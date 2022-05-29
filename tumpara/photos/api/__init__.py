from collections.abc import Sequence
from typing import Optional

import strawberry
from django.db import models

from tumpara import api
from tumpara.gallery.api import (
    GalleryAssetFilter,
    GalleryAssetNode,
    register_gallery_asset_filter,
)
from tumpara.gallery.models import GalleryAssetModel

from ..models import Photo


@register_gallery_asset_filter
class PhotoGalleryAssetFilter(GalleryAssetFilter):
    include_photos: bool = strawberry.field(
        default=True, description="Whether to include photo results."
    )
    photo_width: Optional[api.IntFilter] = None
    photo_height: Optional[api.IntFilter] = None
    photo_aspect_ratio: Optional[api.FloatFilter] = strawberry.field(
        default=None,
        description="Filter based on the photo's aspect ratio. This is calculated as "
        "`width / height`.",
    )
    photo_megapixels: Optional[api.FloatFilter] = strawberry.field(
        default=None,
        description="Filter based on the photo's approximate resolution in megapixels.",
    )
    photo_aperture_size: Optional[api.FloatFilter] = None
    photo_exposure_time: Optional[api.FloatFilter] = None
    photo_focal_length: Optional[api.FloatFilter] = None
    photo_iso_value: Optional[api.IntFilter] = None

    def build_query(
        self, info: api.InfoType, field_name: Optional[str]
    ) -> tuple[models.Q, dict[str, models.Expression | models.F]]:
        prefix = field_name + "__" if field_name else ""
        prefix = f"{prefix}photo_instance__"
        query, aliases = super().build_query(info, field_name)

        if not self.include_photos:
            query &= models.Q((f"{prefix}isnull", True))
            return query, aliases

        subquery = models.Q()

        for attribute_name in [
            "width",
            "height",
            "aperture_size",
            "exposure_time",
            "focal_length",
            "iso_value",
        ]:
            filter: Optional[api.IntFilter | api.FloatFilter] = getattr(
                self, f"photo_{attribute_name}", None
            )
            if filter is not None:
                subquery &= filter.build_query(info, prefix + attribute_name)
        if self.photo_aspect_ratio:
            alias = f"_{field_name}_photo_aspect_ratio"
            aliases[alias] = models.F(f"{prefix}width") / models.F(f"{prefix}width")
            subquery &= self.photo_aspect_ratio.build_query(info, alias)
        if self.photo_megapixels:
            alias = f"_{field_name}_photo_megapixels"
            aliases[alias] = (
                models.F(f"{prefix}width") * models.F(f"{prefix}width") / 1000000
            )
            subquery &= self.photo_megapixels.build_query(info, alias)

        query &= models.Q((f"{prefix}isnull", True)) | subquery
        return query, aliases

    def get_instance_types(self) -> Sequence[type[GalleryAssetModel]]:
        return [*super().get_instance_types(), Photo]


@api.remove_duplicate_node_interface
@strawberry.type(name="Photo", description="A photo scanned in a library.")
class PhotoNode(
    GalleryAssetNode,
    api.DjangoNode,
    fields=[
        "width",
        "height",
        "camera_make",
        "camera_model",
        "iso_value",
        "exposure_time",
        "aperture_size",
        "focal_length",
        "blurhash",
    ],
):
    obj: strawberry.Private[Photo]
