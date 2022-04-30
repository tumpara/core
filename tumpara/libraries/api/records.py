import enum
from typing import Optional

import strawberry
from django.db import models

from tumpara import api
from tumpara.libraries import models as libraries_models

from .libraries import LibraryNode


@strawberry.type(name="File")
class FileNode(api.DjangoNode[libraries_models.File], fields=["path"]):
    pass


@strawberry.type
class FileEdge(api.Edge[FileNode]):
    node: FileNode


@strawberry.type(description="A connection to a list of files.")
class FileConnection(
    api.DjangoConnection[FileNode, libraries_models.File],
    name="file",
    pluralized_name="files",
):
    edges: list[Optional[FileEdge]]
    nodes: list[Optional[FileNode]]


@strawberry.enum
class RecordVisibility(enum.Enum):
    PUBLIC = libraries_models.Visibility.PUBLIC
    INTERNAL = libraries_models.Visibility.INTERNAL
    MEMBERS = libraries_models.Visibility.MEMBERS
    OWNERS = libraries_models.Visibility.OWNERS
    INHERIT = libraries_models.Visibility.INHERIT


@strawberry.interface(name="Record")
class RecordNode(
    api.DjangoNode[libraries_models.Record], fields=["library", "visibility"]
):
    library: Optional[LibraryNode]
    visibility: RecordVisibility

    @api.DjangoConnectionField(
        FileConnection,
        description="Each record may have files attached to it. This field returns a "
        "connection to those currently available.",
    )
    def files(self) -> models.QuerySet[libraries_models.File]:
        return self._obj.files.filter(availability__isnull=False)


@strawberry.input
class SetRecordVisibilityInput:
    ids: list[strawberry.ID] = strawberry.field(description="Record IDs to update.")
    visibility: RecordVisibility = strawberry.field(
        description="Visibility value that should be set for all records."
    )


@strawberry.type
class SetRecordVisibilitySuccess:
    update_count: int


SetRecordVisibilityResult = strawberry.union(
    "SetRecordVisibilityResult", types=(SetRecordVisibilitySuccess, api.NodeError)
)


@api.schema.mutation
class Mutation:
    @strawberry.field(description="Set the visibility of one or more record(s).")
    def set_record_visibility(
        self, info: api.InfoType, input: SetRecordVisibilityInput
    ) -> SetRecordVisibilityResult:
        primary_keys = set[str]()
        for record_id in input.ids:
            type_name, *key = api.decode_key(record_id)
            origin, _ = api.get_node_origin(type_name, info)

            # This check is crucial - we make sure that the ID is from some kind of
            # record type. Since our inheritance is set up by using a foreign key to
            # the 'record' table as the primary key of the child type, we know that any
            # primary key of the concrete record type will also work on the parent.
            if not issubclass(origin, RecordNode) or not len(key) == 1:
                return api.NodeError(requested_id=record_id)

            primary_keys.add(key[0])

        update_count = (
            libraries_models.Record.objects.for_user(
                "libraries.change_record", info.context.user
            )
            .filter(pk__in=primary_keys)
            .update(visibility=input.visibility.value)
        )

        return SetRecordVisibilitySuccess(update_count=update_count)
