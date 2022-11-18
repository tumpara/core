from collections.abc import Sequence
from typing import Annotated, Optional

import strawberry
from django import urls
from django.conf import settings
from django.core import signing
from django.db import models
from django.db.models import functions

from tumpara import api
from tumpara.libraries.api import AssetFilter, AssetNode, register_asset_filter
from tumpara.libraries.models import AssetModel

from ..models import Photo


@register_asset_filter
class PhotoAssetFilter(AssetFilter):
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

        # Filter out photos with no main path (where we can't generate a thumbnail).
        subquery = ~models.Q((f"{prefix}main_path", ""))

        width_float = functions.Cast(models.F(f"{prefix}width"), models.FloatField())
        height_float = functions.Cast(models.F(f"{prefix}height"), models.FloatField())

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
            aliases[alias] = width_float / height_float
            subquery &= self.photo_aspect_ratio.build_query(info, alias)
        if self.photo_megapixels:
            alias = f"_{field_name}_photo_megapixels"
            aliases[alias] = width_float * height_float / 1000000
            subquery &= self.photo_megapixels.build_query(info, alias)

        if subquery:
            query &= models.Q((f"{prefix}isnull", True)) | subquery
        return query, aliases

    def get_instance_types(self) -> Sequence[type[AssetModel]]:
        return [*super().get_instance_types(), Photo]


@api.schema.extra_type
@api.remove_duplicate_node_interface
@strawberry.type(name="Photo", description="A photo scanned in a library.")
class PhotoNode(
    AssetNode,
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

    @strawberry.field(
        description=f"Generate an URL for a thumbnail of this photo. The resulting URL "
        f"will be valid for about {round(settings.API_LINK_VALIDITY_TIME / 60)} "
        f"minute(s)."
    )
    def thumbnail_url(
        self,
        width: Annotated[
            Optional[int],
            strawberry.argument(
                description="Maximum width of the thumbnail. The image will not be "
                "wider than this. Use `null` or `0` to ignore this dimension."
            ),
        ] = None,
        height: Annotated[
            Optional[int],
            strawberry.argument(
                description="Maximum height of the thumbnail. The image will not be "
                "higher than this. Use `null` or `0` to ignore this dimension."
            ),
        ] = None,
    ) -> str:
        description = signing.dumps(
            (self.obj.pk, width, height),
            salt="tumpara.photos.views.render_thumbnail",
        )
        return urls.reverse("photo_thumbnail", args=[description])
