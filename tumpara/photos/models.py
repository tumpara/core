from __future__ import annotations

from fractions import Fraction
from typing import Any, Optional

import PIL.Image
from django.core import validators
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from tumpara.libraries.models import AssetModel, AssetQuerySet, File, Library

from .utils import (
    ImageMetadata,
    calculate_blurhash,
    extract_timestamp_from_filename,
    load_image,
)


class PhotoQuerySet(AssetQuerySet["Photo"]):
    pass


PhotoManager = models.Manager.from_queryset(PhotoQuerySet)


class Photo(AssetModel):
    metadata_checksum = models.BinaryField(
        _("metadata checksum"),
        max_length=32,
        null=True,
        blank=True,
        default=None,
        unique=True,
        help_text="Hash value of the image's metadata and the library ID. This is used "
        "to attribute multiple variations of the same photo to a single asset.",
    )
    main_path = models.CharField(
        _("main path"),
        max_length=File._meta.get_field("path").max_length,
        default="",
        help_text="Path of the main image that should be used for generating "
        "thumbnails and other information.",
    )

    width = models.PositiveIntegerField(
        _("width"),
        null=True,
        blank=True,
    )
    height = models.PositiveIntegerField(
        _("height"),
        null=True,
        blank=True,
    )

    aperture_size = models.FloatField(
        _("aperture size"),
        null=True,
        blank=True,
        validators=[validators.MinValueValidator(0)],
        help_text=_(
            "Aperture / F-Stop value of the shot, in inverse. A value of 4 in this "
            "field implies an f-value of f/4."
        ),
    )
    exposure_time = models.FloatField(
        _("exposure time"),
        null=True,
        blank=True,
        validators=[validators.MinValueValidator(0)],
        help_text=_("The shot's exposure time, in seconds."),
    )
    focal_length = models.FloatField(
        _("focal length"),
        null=True,
        blank=True,
        validators=[validators.MinValueValidator(0)],
        help_text=_("Focal length of the camera, in millimeters."),
    )
    iso_value = models.PositiveIntegerField(
        _("ISO sensitivity value"),
        null=True,
        blank=True,
    )
    flash_description = models.CharField(
        _("flash"),
        max_length=100,
        blank=True,
        help_text=_("As named or identified by the camera vendor. This may be blank."),
    )
    focus_mode_description = models.CharField(
        _("focus mode"),
        max_length=100,
        blank=True,
        help_text=_("As named or identified by the camera vendor. This may be blank."),
    )
    exposure_program_description = models.CharField(
        _("exposure program"),
        max_length=100,
        blank=True,
        help_text=_("As named or identified by the camera vendor. This may be blank."),
    )
    metering_mode_description = models.CharField(
        _("metering mode"),
        max_length=100,
        blank=True,
        help_text=_("As named or identified by the camera vendor. This may be blank."),
    )
    macro_mode_description = models.CharField(
        _("macro mode"),
        max_length=100,
        blank=True,
        help_text=_("As named or identified by the camera vendor. This may be blank."),
    )

    camera_make = models.CharField(_("camera maker"), max_length=50, blank=True)
    camera_model = models.CharField(_("camera model"), max_length=50, blank=True)
    lens_identifier = models.CharField(
        _("lens identifier"),
        max_length=100,
        blank=True,
        help_text=_("Name or ID of the camera lens, if applicable."),
    )

    software = models.CharField(
        _("software"),
        max_length=100,
        blank=True,
        help_text=_("Name of the Software used to edit the image, if any."),
    )

    blurhash = models.CharField(
        "blurhash",
        max_length=100,
        null=True,
        help_text=_(
            "Blurhash textual representation that can be used for loading placeholders."
        ),
    )

    objects = PhotoManager()

    class Meta:
        verbose_name = _("photo")
        verbose_name_plural = _("photos")

    @property
    def exposure_time_fraction(self) -> Optional[Fraction]:
        """Exposure time of the shot, in sections."""
        if self.exposure_time is None:
            return None
        try:
            return Fraction(self.exposure_time).limit_denominator(10000)
        except TypeError:
            return None

    def scan_metadata(self, commit: bool = True) -> None:
        """Update the metadata for this photo object.

        This will re-scan one of the files associated with this record and populate
        the database.
        """
        # Pick one of the files to use as the main source. We mainly want to prefer
        # JPEGs and other non-raw sources because:
        # a) They don't require any post-processing.
        # b) We assume that the user has edited the raw photo and therefore the JPEG (or
        #    whatever format the output has) will probably be more to their liking than
        #    the raw image, or whatever we can automatically develop.
        # c) If the user has not explicitly edited the photo, there might still be an
        #    out-of-camera rendition in JPEG form, which is probably of better quality
        #    than what we can produce.
        self.main_path = ""
        main_image: Optional[PIL.Image.Image] = None
        main_path_raw_original = False
        main_path_pixel_count = 0
        for (path,) in self.files.filter(availability__isnull=False).values_list(
            "path"
        ):
            image, raw_original = load_image(self.library, path)
            pixel_count = image.width * image.height

            # As mentioned before, the picked image will ideally be non-raw. If there
            # are multiple to choose from, we want to end up with the one with the
            # highest resolution.
            if (
                self.main_path == ""
                # Non-raws are better than raws.
                or (main_path_raw_original and not raw_original)
                # If we can get a higher resolution, use that.
                or (
                    main_path_raw_original == raw_original
                    and main_path_pixel_count < pixel_count
                )
            ):
                self.main_path = path
                main_image = image
                main_path_raw_original = raw_original
                main_path_pixel_count = pixel_count

        if main_image is None:
            # This photo object is effectively dead and will be filtered out in the API.
            self.main_path = ""
            if commit:
                self.save()
            return

        assert self.main_path != ""
        image = main_image
        image_metadata = ImageMetadata.load(self.library, self.main_path)

        try:
            self.blurhash = calculate_blurhash(image)
        except:
            self.blurhash = None

        self.media_timestamp = (
            image_metadata.timestamp
            or extract_timestamp_from_filename(self.main_path)
            or timezone.now()
        )

        self.width = image.width
        self.height = image.height

        self.aperture_size = image_metadata.aperture_size
        self.exposure_time = image_metadata.exposure_time
        self.focal_length = image_metadata.focal_length
        self.iso_value = image_metadata.iso_value
        self.flash_description = image_metadata.flash_description
        self.focus_mode_description = image_metadata.focus_mode_description
        self.exposure_program_description = image_metadata.exposure_program_description
        self.metering_mode_description = image_metadata.metering_mode_description
        self.macro_mode_description = image_metadata.macro_mode_description

        self.camera_make = image_metadata.camera_make
        self.camera_model = image_metadata.camera_model
        self.lens_identifier = image_metadata.lens_identifier

        self.software = image_metadata.software

        # TODO Extract GPS information.
        self.media_location = None

        self.full_clean()
        if commit:
            self.save()

    @staticmethod
    def _get_or_create_photo(
        library: Library, metadata_checksum: Optional[bytes], **defaults: Any
    ) -> Photo:
        # Note: metadata_checksum must incorporate the library's primary key (by passing
        # it as a payload to ImageMetadata.calculate_checksum() so that unique
        # constraint in the database works correctly!
        if metadata_checksum is None:
            photo = Photo.objects.create(library=library, **defaults)
        else:
            photo, _ = Photo.objects.get_or_create(
                library=library,
                metadata_checksum=metadata_checksum,
                defaults=defaults,
            )
        return photo

    @staticmethod
    def handle_new_file(
        context: str, path: str, library: Library, **kwargs: Any
    ) -> Optional[Photo]:
        if context != "gallery":
            return None
        try:
            load_image(library, path)
            metadata = ImageMetadata.load(library, path)
        except (IOError, PIL.UnidentifiedImageError):
            return None
        return Photo._get_or_create_photo(
            library,
            metadata.calculate_checksum(payload=library.pk),
        )

    @staticmethod
    def handle_files_changed(sender: type[Photo], asset: Photo, **kwargs: Any) -> None:
        if sender is not Photo or not isinstance(asset, Photo):
            return

        photos = {asset}

        for file in asset.files.filter(availability__isnull=False):
            try:
                load_image(asset.library, file.path)
                image_metadata = ImageMetadata.load(asset.library, file.path)
            except (IOError, PIL.UnidentifiedImageError):
                file.availability = None
                file.save()
            else:
                metadata_checksum = image_metadata.calculate_checksum(
                    payload=asset.library.pk,
                )
                if metadata_checksum != asset.metadata_checksum:
                    # Move the file to another asset if it doesn't match this one.
                    photo = Photo._get_or_create_photo(
                        asset.library,
                        metadata_checksum,
                        visibility=asset.visibility,
                    )
                    photos.add(photo)
                    file.asset = photo
                    file.save()

        for photo in photos:
            photo.scan_metadata()
