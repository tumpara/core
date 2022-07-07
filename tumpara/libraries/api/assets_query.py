"""Assets API query.

This module is loaded separately from ``assets.py`` because it needs to be loaded after
all the filter types have been registered.
"""

from typing import Any

import strawberry
from django.db import models

from tumpara import api

from ..models import Asset
from .assets import AssetConnection, AssetFilter, AssetNode, asset_filter_types

CombinedAssetFilter = strawberry.input(
    description="Filtering options when querying `Asset` objects.\n\n"
    "Most options here are prefixed with the type of asset they apply on. Use the"
    "`include_` options to select which types are returned."
)(type("AssetFilter", tuple(asset_filter_types), {}))


@api.schema.query
class Query:
    @api.DjangoConnectionField(
        AssetConnection,
        filter_type=CombinedAssetFilter,
        description="This connection contains all assets that are currently available.",
    )
    def assets(self, info: api.InfoType, **kwargs: Any) -> models.QuerySet[Asset]:
        queryset = AssetNode.get_queryset(info, "libraries.view_asset")

        given_filter = kwargs["filter"]
        # While the filter is technically optional in the GraphQL schema, the
        # DjangoConnectionField implementation ensures that there is always a filter
        # instance present when this resolver is called.
        assert isinstance(given_filter, AssetFilter)

        instance_types = given_filter.get_instance_types()
        if len(instance_types) == 0:
            return queryset.none()
        queryset = queryset.resolve_instances(*instance_types)

        # TODO This should become a more refined queryset that automatically prefetches
        #   related models.
        return queryset
