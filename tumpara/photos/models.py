from __future__ import annotations

from typing import Any, Optional

from django.core import validators
from django.db import models
from django.utils.translation import gettext_lazy as _

from tumpara.gallery.models import (
    GalleryAssetManager,
    GalleryAssetModel,
    GalleryAssetQuerySet,
)
from tumpara.libraries.models import Library

from .utils import calculate_metadata_checksum


class PhotoQuerySet(GalleryAssetQuerySet["Photo"]):
    pass


PhotoManager = GalleryAssetManager.from_queryset(PhotoQuerySet)


class Photo(GalleryAssetModel):
    metadata_checksum = models.BinaryField(
        _("metadata checksum"),
        max_length=32,
        db_index=True,
        help_text="Hash value of the image's metadata. This is used to attribute "
        "multiple variations of the same photo to a single asset.",
    )

    width = models.PositiveIntegerField(_("width"))
    height = models.PositiveIntegerField(_("height"))

    camera_make = models.CharField(
        _("camera maker"), max_length=50, null=True, blank=True
    )
    camera_model = models.CharField(
        _("camera model"), max_length=50, null=True, blank=True
    )

    iso_value = models.PositiveIntegerField(
        _("ISO sensitivity value"), null=True, blank=True
    )
    exposure_time = models.DecimalField(
        _("exposure time"),
        null=True,
        blank=True,
        max_digits=8,
        decimal_places=4,
        validators=(
            validators.MinValueValidator(0.0001),
            validators.MaxValueValidator(9999),
        ),
        help_text=_("The shot's exposure time, in seconds."),
    )
    aperture_size = models.DecimalField(
        _("aperture size"),
        null=True,
        blank=True,
        max_digits=3,
        decimal_places=1,
        validators=(validators.MinValueValidator(1), validators.MaxValueValidator(100)),
        help_text=_(
            "Aperture / F-Stop value of the shot, in inverse. A value of 4 in this "
            "field implies an f-value of f/4."
        ),
    )
    focal_length = models.FloatField(
        _("focal length"),
        null=True,
        blank=True,
        help_text=_("Focal length of the camera, in millimeters."),
    )

    objects = PhotoManager()

    class Meta:
        verbose_name = _("photo")
        verbose_name_plural = _("photos")

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
        photo, _ = Photo.objects.get_or_create(
            library=library, metadata_checksum=metadata_checksum
        )
        return photo

    @staticmethod
    def handle_files_changed(sender: type[Photo], asset: Photo, **kwargs: Any) -> None:
        if sender is not Photo or not isinstance(asset, Photo):
            return

        for file in asset.files.filter(availability__isnull=False):
            try:
                metadata_checksum = calculate_metadata_checksum(
                    asset.library, file.path
                )
            except IOError:
                file.availability = False
                file.save()
            else:
                if metadata_checksum != asset.metadata_checksum:
                    # Move the file to another asset if it doesn't match this one.
                    photo, _ = Photo.objects.get_or_create(
                        library=asset.library, metadata_checksum=metadata_checksum
                    )
                    file.asset = photo
                    file.save()
