from typing import Any

import strawberry
from django.db import models

from tumpara import api

from ..models import GalleryRecord, GalleryRecordModel
from .gallery_records import (
    GalleryRecordConnection,
    GalleryRecordFilter,
    GalleryRecordNode,
    gallery_record_filter_types,
)

CombinedGalleryRecordFilter = strawberry.input(
    description="Filtering options when querying `GalleryRecord` objects."
)(type("GalleryRecordFilter", tuple(gallery_record_filter_types), {}))


@api.schema.query
class Query:
    @api.DjangoConnectionField(
        GalleryRecordConnection,
        filter_type=CombinedGalleryRecordFilter,
        description="This connection contains all gallery records that are currently "
        "available.",
    )
    def gallery_records(
        self, info: api.InfoType, **kwargs: Any
    ) -> models.QuerySet[GalleryRecord]:
        queryset = GalleryRecordNode.get_queryset(info, "gallery.view_galleryrecord")

        filter = kwargs["filter"]
        # While the filter is technically optional in the GraphQL schema, the
        # DjangoConnectionField implementation ensures that there is always a filter
        # instance present when this resolver is called.
        assert isinstance(filter, GalleryRecordFilter)

        instance_types = filter.get_instance_types()
        if len(instance_types) == 0:
            return queryset.none()
        queryset = queryset.resolve_instances(*instance_types)

        # TODO This should become a more refined queryset that automatically prefetches
        #   related models.
        return queryset
