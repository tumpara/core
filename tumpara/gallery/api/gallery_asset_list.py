from typing import Any

import strawberry
from django.db import models

from tumpara import api

from ..models import GalleryAsset
from .gallery_assets import (
    GalleryAssetConnection,
    GalleryAssetFilter,
    GalleryAssetNode,
    gallery_asset_filter_types,
)

CombinedGalleryAssetFilter = strawberry.input(
    description="Filtering options when querying `GalleryAsset` objects.\n\n"
    "Most options here are prefixed with the type of asset they apply on. Use the"
    "`include_` options to select which types are returned."
)(type("GalleryAssetFilter", tuple(gallery_asset_filter_types), {}))


@api.schema.query
class Query:
    @api.DjangoConnectionField(
        GalleryAssetConnection,
        filter_type=CombinedGalleryAssetFilter,
        description="This connection contains all gallery assets that are currently "
        "available.",
    )
    def gallery_assets(
        self, info: api.InfoType, **kwargs: Any
    ) -> models.QuerySet[GalleryAsset]:
        queryset = GalleryAssetNode.get_queryset(info, "gallery.view_galleryasset")

        filter = kwargs["filter"]
        # While the filter is technically optional in the GraphQL schema, the
        # DjangoConnectionField implementation ensures that there is always a filter
        # instance present when this resolver is called.
        assert isinstance(filter, GalleryAssetFilter)

        instance_types = filter.get_instance_types()
        if len(instance_types) == 0:
            return queryset.none()
        queryset = queryset.resolve_instances(*instance_types)

        # TODO This should become a more refined queryset that automatically prefetches
        #   related models.
        return queryset
