import enum
from collections.abc import Sequence, Set
from typing import Optional

import strawberry
from django.db import models

from tumpara import api
from tumpara.accounts.utils import build_permission_name
from tumpara.libraries.models import File, Record, RecordQuerySet, Visibility

from .libraries import LibraryNode


@strawberry.type(name="File")
class FileNode(api.DjangoNode[File], fields=["path"]):
    pass


@strawberry.type
class FileEdge(api.Edge[FileNode]):
    node: FileNode


@strawberry.type(description="A connection to a list of files.")
class FileConnection(
    api.DjangoConnection[FileNode, File],
    name="file",
    pluralized_name="files",
):
    edges: list[Optional[FileEdge]]
    nodes: list[Optional[FileNode]]


@strawberry.enum
class RecordVisibility(enum.Enum):
    PUBLIC = Visibility.PUBLIC
    INTERNAL = Visibility.INTERNAL
    MEMBERS = Visibility.MEMBERS
    OWNERS = Visibility.OWNERS
    FROM_LIBRARY = Visibility.FROM_LIBRARY


@strawberry.input(description="Filtering options for record visibility fields.")
class RecordVisibilityFilter:
    public: bool = strawberry.field(
        default=True, description="Whether to include public records."
    )
    internal: bool = strawberry.field(
        default=True, description="Whether to include internal records."
    )
    members: bool = strawberry.field(
        default=True,
        description="Whether to include records visible only to library members.",
    )
    owners: bool = strawberry.field(
        default=True,
        description="Whether to include records visible only to library owners.",
    )
    public_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include public records, where the visibility has been"
        "inherited from the library. By default (or when set to `null`) this will take"
        "the same value as the `public` option.",
    )
    internal_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include internal records, where the visibility has been"
        "inherited from the library. By default (or when set to `null`) this will take"
        "the same value as the `internal` option.",
    )
    members_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include records visible only to library members, where"
        "the visibility has been inherited from the library. By default (or when set "
        "to `null`) this will take the same value as the `members` option.",
    )
    owners_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include records visible only to library owners, where"
        "the visibility has been inherited from the library. By default (or when set "
        "to `null`) this will take the same value as the `owners` option.",
    )

    def build_query(
        self, visibility_field_name: str, library_visibility_field_name: str
    ) -> models.Q:
        query = models.Q()
        if self.public:
            query |= models.Q((visibility_field_name, Visibility.PUBLIC))
        if self.internal:
            query |= models.Q((visibility_field_name, Visibility.INTERNAL))
        if self.members:
            query |= models.Q((visibility_field_name, Visibility.MEMBERS))
        if self.owners:
            query |= models.Q((visibility_field_name, Visibility.OWNERS))

        subquery = models.Q()
        if self.public_from_library or (
            self.public_from_library is None and self.public
        ):
            subquery |= models.Q((library_visibility_field_name), Visibility.PUBLIC)
        if self.internal_from_library or (
            self.internal_from_library is None and self.internal
        ):
            subquery |= models.Q((library_visibility_field_name), Visibility.INTERNAL)
        if self.members_from_library or (
            self.members_from_library is None and self.members
        ):
            subquery |= models.Q((library_visibility_field_name), Visibility.MEMBERS)
        if self.owners_from_library or (
            self.owners_from_library is None and self.owners
        ):
            subquery |= models.Q((library_visibility_field_name), Visibility.OWNERS)

        if subquery != models.Q():
            query |= (
                models.Q((visibility_field_name, Visibility.FROM_LIBRARY)) & subquery
            )

        return query


@strawberry.interface(name="Record")
class RecordNode(api.DjangoNode[Record], fields=["library", "visibility"]):
    library: Optional[LibraryNode]
    visibility: RecordVisibility

    @api.DjangoConnectionField(
        FileConnection,
        description="Each record may have files attached to it. This field returns a "
        "connection to those currently available.",
    )
    def files(self) -> models.QuerySet[File]:
        return self._obj.files.filter(availability__isnull=False)

    @classmethod
    def get_queryset(
        cls, info: api.InfoType, permission: str
    ) -> models.QuerySet[Record]:
        model = cls._get_model_type()
        manager = model._default_manager
        if not issubclass(manager._queryset_class, RecordQuerySet):  # type: ignore
            raise NotImplementedError
        resolved_permission = permission or build_permission_name(model, "view")
        return manager.for_user(info.context.user, resolved_permission)  # type: ignore

    @classmethod
    def extract_primary_keys_from_ids(
        cls, info: api.InfoType, ids: Sequence[strawberry.ID]
    ) -> api.NodeError | Set[str]:
        """Extract primary keys from a list of node IDs.

        If one of the provided IDs does not belong to this record type, a
        :class:`api.NodeError` will be returned. Also note that this method not validate
        the IDs in any way - neither if they actually belong to an existing record
        object nor if the user has adequate permissions.
        """
        primary_keys = set[str]()
        for record_id in ids:
            type_name, *key = api.decode_key(record_id)
            origin, _ = api.get_node_origin(type_name, info)

            # This check is crucial - we make sure that the ID is from some kind of
            # record type. Since our inheritance is set up by using a foreign key to
            # the 'record' table as the primary key of the child type, we know that any
            # primary key of the concrete record type will also work on the parent.
            if not issubclass(origin, RecordNode) or not len(key) == 1:
                return api.NodeError(requested_id=record_id)

            primary_keys.add(key[0])
        return primary_keys


@strawberry.input
class SetRecordVisibilityInput:
    ids: list[strawberry.ID] = strawberry.field(
        description="Record IDs to update. IDs for records that do not exist will"
        "silently be dropped, invalid IDs will return a `NodeError`."
    )
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
        primary_keys = RecordNode.extract_primary_keys_from_ids(info, input.ids)
        if isinstance(primary_keys, api.NodeError):
            return primary_keys
        update_count = (
            Record.objects.for_user(info.context.user, "libraries.change_record")
            .filter(pk__in=primary_keys)
            .update(visibility=input.visibility.value)
        )
        return SetRecordVisibilitySuccess(update_count=update_count)
