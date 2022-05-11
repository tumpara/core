from collections.abc import Sequence
from typing import Optional

import strawberry
from django.db import models

from tumpara import api
from tumpara.libraries.api import RecordNode, RecordVisibilityFilter

from ..models import GalleryRecord, GalleryRecordModel, GalleryRecordQuerySet


class GalleryRecordFilter:
    def build_query(
        self, field_name: Optional[str]
    ) -> tuple[models.Q, dict[str, models.Expression]]:
        return models.Q(), {}

    def get_instance_types(self) -> Sequence[type[GalleryRecordModel]]:
        """List of instance types that should be passed to
        :meth:`GalleryRecordQuerySet.resolve_instances`"""
        return []


gallery_record_filter_types = list[type[GalleryRecordFilter]]()


def register_gallery_record_filter(
    filter_type: type[GalleryRecordFilter],
) -> type[GalleryRecordFilter]:
    prepped_type = api.schema.prep_type(filter_type, is_input=True)
    gallery_record_filter_types.append(prepped_type)
    return prepped_type


@register_gallery_record_filter
class MainGalleryRecordFilter(GalleryRecordFilter):
    media_timestamp: Optional[api.DateTimeFilter] = None
    visibility: Optional[RecordVisibilityFilter] = None

    def build_query(
        self, field_name: Optional[str]
    ) -> tuple[models.Q, dict[str, models.Expression]]:
        prefix = field_name + "__" if field_name else ""
        query, aliases = super().build_query(field_name)

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
class GalleryRecordNode(RecordNode, api.DjangoNode, fields=["media_timestamp"]):
    obj: strawberry.Private[GalleryRecord]


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

    @classmethod
    def create_node(cls, obj: GalleryRecordModel) -> GalleryRecordNode:
        from ..models import Note
        from .notes import NoteNode

        if isinstance(obj, Note):
            return NoteNode(obj)
        else:
            raise TypeError(f"unsupported gallery record type: {type(obj)}")


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
        if not isinstance(node, GalleryRecordNode):
            return api.NodeError(requested_id=id)
        node.obj.represent_stack()
        return node
