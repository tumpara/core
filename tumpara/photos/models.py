from __future__ import annotations

import logging
import os
from fractions import Fraction
from typing import Any, Literal, Optional, cast

import PIL.Image
from django.conf import settings
from django.core import validators
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from tumpara.libraries.models import AssetModel, AssetQuerySet, File, Library
from tumpara.libraries.scanner.events import NotMyFileAnymore
from tumpara.utils import precisest_datetime

from .types import ImmutableImage
from .utils import (
    AVIF_SUPPORTED,
    ImageMetadata,
    calculate_blurhash,
    extract_timestamp_from_filename,
    load_image,
)

_logger = logging.getLogger(__name__)


class PhotoQuerySet(AssetQuerySet["Photo"]):
    pass


PhotoManager = models.Manager.from_queryset(PhotoQuerySet)


class Photo(AssetModel):
    """Asset type for photos.

    A photo is identified by a hash of its metadata. This hash contains things like the
    hardware used to take it. It is used to identify multiple recordings / renditions
    of the same photo, for example when the user has both a raw image file and an edited
    version of the same picture in their library. Both these file will end up linked to
    the same photo asset.

    The :attr:`~tumpara.libraries.models.File.extra` field contains each file's MIME
    type.
    """

    metadata_checksum = models.BinaryField(
        _("metadata checksum"),
        max_length=32,
        null=True,
        blank=True,
        default=None,
        help_text="Hash value of the image's metadata and the library ID. This is used "
        "to attribute multiple variations / renditions of the same photo to a single "
        "asset.",
    )
    main_path = models.CharField(
        _("main path"),
        max_length=File._meta.get_field("path").max_length,
        default="",
        blank=True,
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
        default="",
        blank=True,
        help_text=_(
            "Blurhash textual representation that can be used for loading placeholders."
        ),
    )

    objects = PhotoManager()

    class Meta:
        verbose_name = _("photo")
        verbose_name_plural = _("photos")
        constraints = [
            models.UniqueConstraint(
                condition=models.Q(metadata_checksum__isnull=False),
                fields=("metadata_checksum",),
                name="photos_unique_by_metadata",
            )
        ]

    @property
    def exposure_time_fraction(self) -> Optional[Fraction]:
        """Exposure time of the shot, in sections."""
        if self.exposure_time is None:
            return None
        try:
            return Fraction(self.exposure_time).limit_denominator(10000)
        except TypeError:
            return None

    @transaction.atomic
    def _find_image(
        self, *, commit: bool = True
    ) -> Optional[tuple[ImmutableImage, ImageMetadata]]:
        old_main_path = self.main_path

        PIL.Image.init()
        image_mime_types = set(PIL.Image.MIME.values())

        candidates = list[tuple[str, str]](
            self.files.filter(availability__isnull=False).values_list("path", "extra")
        )

        # Prefer non-raw images to raw images, because that's probably a better
        # rendition than what rawpy will produce. This setting should be configurable
        # in the future.
        maybe_raw: bool = True
        self.main_path = ""
        image_candidate_paths = {
            path for path, mime_type in candidates if mime_type in image_mime_types
        }
        if image_candidate_paths:
            maybe_raw = False
            # Use the newest rendition that is available.
            self.main_path = sorted(
                image_candidate_paths,
                key=lambda path: self.library.storage.get_modified_time(path),
            )[-1]
        else:
            raw_candidate_paths = {
                path
                for path, mime_type in candidates
                if path not in image_candidate_paths
                and mime_type not in ImageMetadata.SIDECAR_MIME_TYPES
            }
            if raw_candidate_paths:
                self.main_path = sorted(
                    raw_candidate_paths,
                    key=lambda path: self.library.storage.get_modified_time(path),
                )[-1]

        if not self.main_path:
            self.blurhash = ""
            if commit:
                self.save(update_fields=("main_path", "blurhash"))
            raise FileNotFoundError(f"no main file available for photo {self.pk}")

        if self.main_path == old_main_path:
            return None

        mutable_image, _ = load_image(self.library, self.main_path, maybe_raw=maybe_raw)
        image = cast(ImmutableImage, mutable_image)
        image_metadata = ImageMetadata.load(self.library, self.main_path)
        # Make sure the metadata matches that of the image we are displaying.
        self._import_metadata(image_metadata, reset_main_path=False)

        try:
            self.blurhash = calculate_blurhash(image)
        except:
            self.blurhash = ""

        if settings.PRERENDER_THUMBNAILS:
            for format_name in ("avif", "webp"):
                if format_name == "avif" and not AVIF_SUPPORTED:
                    continue
                for size in [(None, 400)]:
                    self.render_thumbnail(
                        format_name,
                        *size,
                        old_main_path != self.main_path,
                        image=image.copy(),
                    )

        if commit:
            self.save()
        return image, image_metadata

    def render_thumbnail(
        self,
        format_name: str,
        requested_width: Optional[int],
        requested_height: Optional[int],
        rerender: bool = False,
        *,
        image: Optional[PIL.Image.Image] = None,
    ) -> str:
        """Render a photo thumbnail to the cache and return its path inside the
        thumbnail storage."""
        directory = hex(self.pk & 0xFF)[2:].zfill(2)
        subdirectory = hex(self.pk & 0xFF00)[2:4].zfill(2)

        absolute_directory_path = settings.THUMBNAIL_STORAGE.path(
            os.path.join(directory, subdirectory)
        )
        if not os.path.isdir(absolute_directory_path):
            os.makedirs(absolute_directory_path, exist_ok=True)

        filename = f"{self.pk}_{requested_width}x{requested_height}.{format_name}"
        path = os.path.join(directory, subdirectory, filename)

        if rerender or not settings.THUMBNAIL_STORAGE.exists(path):
            if image is None:
                if not self.main_path:
                    find_image_result = self._find_image()
                    if find_image_result is not None:
                        image = find_image_result[0]
                if image is None:
                    image, _ = load_image(self.library, self.main_path)
            image.thumbnail(
                (
                    # This means that both None and 0 evaluate to the original
                    # dimensions. An empty API call to thumbnailUrl() will therefore
                    # render the image as-is.
                    requested_width or image.width,
                    requested_height or image.height,
                ),
                PIL.Image.BICUBIC,
            )

            with settings.THUMBNAIL_STORAGE.open(path, "wb") as file_io:
                image.save(file_io, format=format_name.upper())

        return path

    @staticmethod
    def _get_or_create_photo(
        library: Library, metadata_checksum: Optional[bytes], **defaults: Any
    ) -> tuple[Photo, bool]:
        # Note: metadata_checksum must incorporate the library's primary key (by passing
        # it as a payload to ImageMetadata.calculate_checksum() so that unique
        # constraint in the database works correctly!
        if metadata_checksum is None:
            return Photo.objects.create(library=library, **defaults), True
        else:
            return Photo.objects.get_or_create(
                library=library,
                metadata_checksum=metadata_checksum,
                defaults=defaults,
            )

    def _import_metadata(
        self, image_metadata: ImageMetadata, *, reset_main_path: bool = True
    ) -> None:
        """Merge image metadata from the given metadata object with this asset.

        In most cases, this prefers information from the parameter to the already
        present information.
        """
        # Note that precisest_datetime() prefers timestamps earlier in time. This
        # matches what we want here, because if we have an older record of this image,
        # that should be its timestamp (even if it has been edited later on).
        self.media_timestamp = (
            precisest_datetime(self.media_timestamp, image_metadata.timestamp)
            or extract_timestamp_from_filename(image_metadata.file_basename)
            or timezone.now()
        )

        # For these other attributes, prefer the new values. When rendering a thumbnail
        # and picking one of the image files to do so, this method is called, and we
        # want metadata to match what the user is seeing. Plus, this makes scanning a
        # bit more resilient against old metadata.
        # On the downside, this means that we don't prioritize sidecar files, which we
        # arguably should. That means, if we have a JSON (from some online gallery
        # export like Google Takeout) that contains whatever the user had set in the
        # previous online UI, we'd prefer the actual metadata to whatever was set there.
        # But that's only a problem when metadata differs, not when it only exists in
        # one source. The common use case of tagging locations afterward is still
        # covered here.
        if image_metadata.width:
            self.width = image_metadata.width
        if image_metadata.height:
            self.height = image_metadata.height
        if image_metadata.aperture_size:
            self.aperture_size = image_metadata.aperture_size
        if image_metadata.exposure_time:
            self.exposure_time = image_metadata.exposure_time
        if image_metadata.focal_length:
            self.focal_length = image_metadata.focal_length
        if image_metadata.iso_value:
            self.iso_value = image_metadata.iso_value
        if image_metadata.flash_description:
            self.flash_description = image_metadata.flash_description
        if image_metadata.focus_mode_description:
            self.focus_mode_description = image_metadata.focus_mode_description
        if image_metadata.exposure_program_description:
            self.exposure_program_description = (
                image_metadata.exposure_program_description
            )
        if image_metadata.metering_mode_description:
            self.metering_mode_description = image_metadata.metering_mode_description
        if image_metadata.macro_mode_description:
            self.macro_mode_description = image_metadata.macro_mode_description
        if image_metadata.camera_make:
            self.camera_make = image_metadata.camera_make
        if image_metadata.camera_model:
            self.camera_model = image_metadata.camera_model
        if image_metadata.lens_identifier:
            self.lens_identifier = image_metadata.lens_identifier

        # TODO Extract GPS information.
        self.media_location = None

        # Reset the stored main path so that the next _find_image() call will re-save
        # metadata. This makes sure we are prioritizing metadata from the same image
        # that also produced the thumbnail.
        if reset_main_path:
            self.main_path = ""

        self.full_clean()

    @staticmethod
    @transaction.atomic
    def handle_new_file(
        context: str, path: str, library: Library, **kwargs: Any
    ) -> Optional[tuple[Photo, str]]:
        if context != "gallery":
            return None
        try:
            image_metadata = ImageMetadata.load(library, path)
        except IOError:
            return None

        pass
        photo: Photo

        if image_metadata.deriver_name:
            deriver_path = os.path.join(
                os.path.dirname(path), image_metadata.deriver_name
            )
            try:
                photo = Photo.objects.get(
                    library=library,
                    file__path=deriver_path,
                    file__availability__isnull=False,
                )
                pass
            except Photo.DoesNotExist:
                # This file is a sidecar file, but we haven't found the corresponding
                # image file yet. In that case, we can create a new Photo asset (which
                # will have this new file added by the event handler that calls this
                # function) and add the deriver path as a dummy File object, which will
                # be populated once the actual image is found.
                photo = Photo.objects.create(library=library)
                try:
                    deriver_file = File.objects.get(
                        asset__library=library,
                        path=deriver_path,
                        # Don't need to search for availability here, because that would
                        # have been handled above.
                    )
                except File.DoesNotExist:
                    File.objects.create(
                        asset=photo, path=deriver_path, digest="", availability=None
                    )
                else:
                    deriver_file.asset = photo
                    deriver_file.availability = None
                    deriver_file.save(update_fields=("asset", "availability"))

        else:
            # This should be an actual image file (not a sidecar). In case we don't have
            # enough information to calculate a metadata checksum (which would identify
            # multiple renditions of the same photo), create a new asset for this file.
            metadata_checksum = image_metadata.calculate_checksum(payload=library.pk)
            if metadata_checksum is None:
                photo = Photo(library=library)
            else:
                # Check and see if this photo is already on record. If not, create a
                # new asset.
                photo, _ = Photo.objects.get_or_create(
                    library=library, metadata_checksum=metadata_checksum
                )

        photo._import_metadata(image_metadata)
        photo.save()
        return photo, image_metadata.mime_type

    def handle_file_change(self, file: File) -> None:
        try:
            image_metadata = ImageMetadata.load(self.library, file.path)
        except IOError:
            file.availability = None
            file.save(update_fields=("availability",))
            return
        file.extra = image_metadata.mime_type

        metadata_checksum = image_metadata.calculate_checksum(payload=self.library.pk)
        if (
            self.metadata_checksum
            and bytes(self.metadata_checksum) != metadata_checksum
        ):
            raise NotMyFileAnymore

        if image_metadata.deriver_name is not None:
            if not any(
                os.path.basename(path) == image_metadata.deriver_name
                for (path,) in self.files.filter(
                    availability__isnull=False
                ).values_list("path")
            ):
                # This is a sidecar file, but the corresponding actual image file (the
                # deriver) does not belong to this asset.
                raise NotMyFileAnymore

        self._import_metadata(image_metadata)
        self.save()

    @staticmethod
    def handle_scan_finished(
        sender: Literal["scan"], library: Library, **kwargs: Any
    ) -> None:
        photo_queryset = Photo.objects.filter(
            models.Exists(
                File.objects.filter(
                    asset=models.OuterRef("pk"), availability__isnull=False
                )
            ),
            main_path="",
        ).select_related("library")
        _logger.debug(
            f"Scanning image files for {photo_queryset.count()} photo(s). This might "
            f"take a while."
        )
        for photo in photo_queryset:
            photo._find_image()
