from typing import Optional

import strawberry
from django.db import models

from tumpara import api
from tumpara.libraries.api import RecordNode

from ..models import GalleryRecord


@api.remove_duplicate_node_interface
@strawberry.interface(name="GalleryRecord")
class GalleryRecordNode(
    RecordNode, api.DjangoNode[GalleryRecord], fields=["media_timestamp"]
):
    pass


@strawberry.type
class GalleryRecordEdge(api.Edge[GalleryRecordNode]):
    node: GalleryRecordNode


@strawberry.type(description="A connection to a list of gallery records.")
class GalleryRecordConnection(
    api.DjangoConnection[GalleryRecordNode, GalleryRecord],
    name="gallery record",
    pluralized_name="gallery records",
):
    edges: list[Optional[GalleryRecordEdge]]
    nodes: list[Optional[GalleryRecordNode]]


@api.schema.query
class Query:
    @api.DjangoConnectionField(
        GalleryRecordConnection,
        description="This connection contains all gallery records that are currently "
        "available.",
    )
    def gallery_records(self, info: api.InfoType) -> models.QuerySet[GalleryRecord]:
        # TODO This should become a more refined queryset that automatically prefetches
        #   related models.
        return GalleryRecordNode.get_queryset(info)
