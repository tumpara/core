from __future__ import annotations

import os.path
from fractions import Fraction
from typing import Any, Optional, cast

import PIL
from django.core import validators
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from tumpara.gallery.models import (
    GalleryAssetManager,
    GalleryAssetModel,
    GalleryAssetQuerySet,
)
from tumpara.libraries.models import Library

from .utils import (
    calculate_blurhash,
    calculate_metadata_checksum,
    extract_metadata_value,
    extract_timestamp_from_filename,
    load_image,
    load_metadata,
)


class PhotoQuerySet(GalleryAssetQuerySet["Photo"]):
    pass


PhotoManager = GalleryAssetManager.from_queryset(PhotoQuerySet)


class Photo(GalleryAssetModel):
    metadata_checksum = models.BinaryField(
        _("metadata checksum"),
        max_length=32,
        null=True,
        default=None,
        db_index=True,
        help_text="Hash value of the image's metadata. This is used to attribute "
        "multiple variations of the same photo to a single asset.",
    )

    width = models.PositiveIntegerField(_("width"), null=True)
    height = models.PositiveIntegerField(_("height"), null=True)

    aperture_size = models.DecimalField(
        _("aperture size"),
        null=True,
        max_digits=3,
        decimal_places=1,
        validators=[validators.MinValueValidator(1), validators.MaxValueValidator(100)],
        help_text=_(
            "Aperture / F-Stop value of the shot, in inverse. A value of 4 in this "
            "field implies an f-value of f/4."
        ),
    )
    exposure_time = models.FloatField(
        _("exposure time"),
        null=True,
        validators=[validators.MinValueValidator(0.0001)],
        help_text=_("The shot's exposure time, in seconds."),
    )
    focal_length = models.FloatField(
        _("focal length"),
        null=True,
        validators=[validators.MinValueValidator(0.0001)],
        help_text=_("Focal length of the camera, in millimeters."),
    )
    iso_value = models.PositiveIntegerField(_("ISO sensitivity value"), null=True)

    camera_make = models.CharField(_("camera maker"), max_length=50, blank=True)
    camera_model = models.CharField(_("camera model"), max_length=50, blank=True)

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
        # Pick one of the files and extract the metadata from there. This approach
        # currently has two flaws, but they should both be negligible for typical usage
        # patterns:
        # a) The file we pick is arbitrary. Since the metadata checksum includes all
        #    fields that we extract, all files should however have the exact same
        #    metadata information encoded, which makes this point moot.
        # b) We need to open the file twice. This might become a problem when using
        #    storage backends where it's more expensive to open (and read) a file twice,
        #    for example network-backed storage. There are two plausible solutions here:
        #    either the storage backend performs some sort of caching or we only read
        #    the file once and pass it to calculate_metadata_checksum() up above and use
        #    it here again.
        first_paths = (
            self.files.filter(availability__isnull=False).values("path").first()
        )
        if first_paths is None:
            # This photo object is effectively dead and will be filtered out in the API.
            return
        first_path = first_paths["path"]

        image = load_image(self.library, first_path)
        metadata = load_metadata(self.library, first_path)

        try:
            self.blurhash = calculate_blurhash(image)
        except:
            self.blurhash = None

        self.media_timestamp = (
            extract_metadata_value(
                metadata,
                timezone.datetime,
                "Exif.Image.DateTimeOriginal",
                "Exif.Image.DateTime",
                "Exif.Image.DateTimeDigitized",
            )
            or extract_timestamp_from_filename(first_path)
            or timezone.now()
        )

        self.width = image.width
        self.height = image.height

        self.camera_make = (
            extract_metadata_value(metadata, str, "Exif.Image.Make") or ""
        )
        self.camera_model = (
            extract_metadata_value(metadata, str, "Exif.Image.Model") or ""
        )
        # Some camera vendors put their name in the model field as well, which is a bit
        # redundant. We would like to be able to concatenate the make and model fields
        # and get a string that nicely describes the camera, so we remove any redundancy
        # here. Otherwise, we might get things like this when putting the make and model
        # together:
        # - "NIKON CORPORATION NIKON D90"
        # - "Canon Canon EOS 5D Mark III"
        # By removing the common prefix from the model field, the two examples above
        # become "NIKON CORPORATION D90" and "Canon EOS 5D Mark III" when put together.
        camera_prefix = os.path.commonprefix(
            [self.camera_make.lower(), self.camera_model.lower()]
        )
        if camera_prefix:
            self.camera_model = self.camera_model[len(camera_prefix) :].strip()

        self.iso_value = extract_metadata_value(
            metadata, int, "Exif.Photo.ISOSpeedRatings"
        )
        self.exposure_time = extract_metadata_value(
            metadata, float, "Exif.Photo.ExposureTime"
        )
        self.aperture_size = extract_metadata_value(
            metadata, float, "Exif.Photo.FNumber", "Exif.Photo.ApertureValue"
        )
        self.focal_length = extract_metadata_value(
            metadata, float, "Exif.Photo.FocalLength"
        )

        # TODO Extract GPS information.
        self.media_location = None

        if commit:
            self.save()

    @staticmethod
    def _get_or_create_photo(
        library: Library, metadata_checksum: Optional[bytes], **kwargs: Any
    ) -> Photo:
        if metadata_checksum is None:
            photo = Photo.objects.create(library=library, **kwargs)
        else:
            photo, _ = Photo.objects.get_or_create(
                library=library, metadata_checksum=metadata_checksum, **kwargs
            )
        return cast(Photo, photo)

    @staticmethod
    def handle_new_file(
        context: str, path: str, library: Library, **kwargs: Any
    ) -> Optional[Photo]:
        if context != "gallery":
            return None
        try:
            metadata_checksum = calculate_metadata_checksum(library, path)
        except IOError:
            return None
        return Photo._get_or_create_photo(library, metadata_checksum)

    @staticmethod
    def handle_files_changed(sender: type[Photo], asset: Photo, **kwargs: Any) -> None:
        if sender is not Photo or not isinstance(asset, Photo):
            return

        photos = {asset}

        for file in asset.files.filter(availability__isnull=False):
            try:
                load_image(asset.library, file.path)
                metadata_checksum = calculate_metadata_checksum(
                    asset.library, file.path
                )
            except (IOError, PIL.UnidentifiedImageError):
                file.availability = None
                file.save()
            else:
                if metadata_checksum != asset.metadata_checksum:
                    # Move the file to another asset if it doesn't match this one.
                    photo = Photo._get_or_create_photo(
                        asset.library, metadata_checksum, visibility=asset.visibility
                    )
                    photos.add(photo)
                    file.asset = photo
                    file.save()

        for photo in photos:
            photo.scan_metadata()
