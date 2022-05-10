from typing import Optional

import strawberry
from django.db import models

from tumpara import api
from tumpara.libraries.api import RecordNode, RecordVisibilityFilter

from ..models import GalleryRecord


@strawberry.input(
    description="Filtering options when querying `GalleryRecord` objects."
)
class GalleryRecordFilter:
    media_timestamp: Optional[api.DateTimeFilter] = None
    visibility: Optional[RecordVisibilityFilter] = None

    def build_query(
        self, field_name: Optional[str]
    ) -> tuple[models.Q, dict[str, models.Expression]]:
        prefix = field_name + "__" if field_name else ""
        query = models.Q()
        aliases = dict[str, models.Expression]()

        if self.media_timestamp is not None:
            next_query, next_aliases = self.media_timestamp.build_query(
                f"{prefix}media_timestamp"
            )
            query &= next_query
            aliases |= next_aliases

        if self.visibility is not None:
            query &= self.visibility.build_query(
                f"{prefix}visibility", f"{prefix}library__visibility"
            )

        return query, aliases


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
        filter_type=GalleryRecordFilter,
        description="This connection contains all gallery records that are currently "
        "available.",
    )
    def gallery_records(self, info: api.InfoType) -> models.QuerySet[GalleryRecord]:
        # TODO This should become a more refined queryset that automatically prefetches
        #   related models.
        return GalleryRecordNode.get_queryset(info, "gallery.view_galleryrecord")  # type: ignore


@strawberry.input
class StackingMutationInput:
    ids: list[strawberry.ID] = strawberry.field(
        description="Gallery record IDs to update. IDs for records that do not exist "
        "will silently be dropped, invalid IDs will return a `NodeError`."
    )


@strawberry.type
class StackingMutationSuccess:
    stack_size: int = strawberry.field(description="Size of the stack.")


StackingMutationResult = strawberry.union(
    "StackingMutationResult", types=(StackingMutationSuccess, api.NodeError)
)
SetStackRepresentativeResult = strawberry.union(
    "StackingMutationResult", types=(GalleryRecordNode, api.NodeError)
)


@api.schema.mutation
class Mutation:
    @strawberry.field(description="Stack the given set of gallery records together.")
    def stack_gallery_records(
        self, info: api.InfoType, input: StackingMutationInput
    ) -> StackingMutationResult:
        primary_keys = GalleryRecordNode.extract_primary_keys_from_ids(info, input.ids)
        if isinstance(primary_keys, api.NodeError):
            return primary_keys
        stack_size = (
            GalleryRecord.objects.for_user(
                info.context.user, "gallery.change_galleryrecord"
            )
            .filter(pk__in=primary_keys)
            .stack()
        )
        return StackingMutationSuccess(stack_size=stack_size)

    @strawberry.field(
        description="Clear the stack of each of the given gallery records."
    )
    def unstack_gallery_records(
        self, info: api.InfoType, input: StackingMutationInput
    ) -> StackingMutationResult:
        primary_keys = GalleryRecordNode.extract_primary_keys_from_ids(info, input.ids)
        if isinstance(primary_keys, api.NodeError):
            return primary_keys
        stack_size = (
            GalleryRecord.objects.for_user(
                info.context.user, "gallery.change_galleryrecord"
            )
            .filter(pk__in=primary_keys)
            .unstack()
        )
        return StackingMutationSuccess(stack_size=stack_size)

    @strawberry.field(description="Make.")
    def set_stack_representative(
        self, info: api.InfoType, id: strawberry.ID
    ) -> SetStackRepresentativeResult:
        node = api.resolve_node(info, id, "gallery.change_galleryrecord")
        if not isinstance(node, GalleryRecord):
            return api.NodeError(requested_id=id)
        node._obj.represent_stack()
        return node
