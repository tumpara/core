import dataclasses
import enum
from collections.abc import Sequence, Set
from typing import Any, Optional

import strawberry
from django.db import models

from tumpara import api
from tumpara.accounts.utils import build_permission_name

from ..models import Asset, AssetQuerySet, File, Visibility
from .libraries import LibraryNode


@strawberry.type(name="File")
class FileNode(api.DjangoNode, fields=["path"]):
    obj: strawberry.Private[File]


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
class AssetVisibility(enum.Enum):
    PUBLIC = Visibility.PUBLIC
    INTERNAL = Visibility.INTERNAL
    MEMBERS = Visibility.MEMBERS
    OWNERS = Visibility.OWNERS
    FROM_LIBRARY = Visibility.FROM_LIBRARY


@strawberry.input(description="Filtering options for asset visibility fields.")
class AssetVisibilityFilter:
    public: bool = strawberry.field(
        default=True, description="Whether to include public assets."
    )
    internal: bool = strawberry.field(
        default=True, description="Whether to include internal assets."
    )
    members: bool = strawberry.field(
        default=True,
        description="Whether to include assets visible only to library members.",
    )
    owners: bool = strawberry.field(
        default=True,
        description="Whether to include assets visible only to library owners.",
    )
    public_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include public assets, where the visibility has been"
        "inherited from the library. By default (or when set to `null`) this will take"
        "the same value as the `public` option.",
    )
    internal_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include internal assets, where the visibility has been"
        "inherited from the library. By default (or when set to `null`) this will take"
        "the same value as the `internal` option.",
    )
    members_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include assets visible only to library members, where"
        "the visibility has been inherited from the library. By default (or when set "
        "to `null`) this will take the same value as the `members` option.",
    )
    owners_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include assets visible only to library owners, where"
        "the visibility has been inherited from the library. By default (or when set "
        "to `null`) this will take the same value as the `owners` option.",
    )

    def build_query(
        self,
        info: api.InfoType,
        visibility_field_name: str,
        library_default_visibility_field_name: str,
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
            subquery |= models.Q(
                (library_default_visibility_field_name, Visibility.PUBLIC)
            )
        if self.internal_from_library or (
            self.internal_from_library is None and self.internal
        ):
            subquery |= models.Q(
                (library_default_visibility_field_name, Visibility.INTERNAL)
            )
        if self.members_from_library or (
            self.members_from_library is None and self.members
        ):
            subquery |= models.Q(
                (library_default_visibility_field_name, Visibility.MEMBERS)
            )
        if self.owners_from_library or (
            self.owners_from_library is None and self.owners
        ):
            subquery |= models.Q(
                (library_default_visibility_field_name, Visibility.OWNERS)
            )

        if subquery != models.Q():
            query |= (
                models.Q((visibility_field_name, Visibility.FROM_LIBRARY)) & subquery
            )

        return query


@strawberry.interface(name="Asset")
class AssetNode(api.DjangoNode, fields=["library", "visibility"]):
    obj: strawberry.Private[Asset]
    # The explicit fields here are to please MyPy:
    library: Optional[LibraryNode] = dataclasses.field(init=False)
    visibility: AssetVisibility = dataclasses.field(init=False)

    @api.DjangoConnectionField(
        FileConnection,
        description="Each asset may have files attached to it. This field returns a "
        "connection to those currently available.",
    )
    def files(self, info: api.InfoType, **kwargs: Any) -> models.QuerySet[File]:
        return self.obj.files.filter(availability__isnull=False)

    @classmethod
    def get_queryset(cls, info: api.InfoType, permission: str) -> AssetQuerySet[Any]:
        model = cls._get_model_type()
        assert issubclass(model, Asset)
        resolved_permission = permission or build_permission_name(model, "view")
        return model._default_manager.for_user(
            info.context.user, resolved_permission
        ).resolve_instances()

    @classmethod
    def extract_primary_keys_from_ids(
        cls, info: api.InfoType, ids: Sequence[strawberry.ID]
    ) -> api.NodeError | Set[str]:
        """Extract primary keys from a list of node IDs.

        If one of the provided IDs does not belong to this asset type, a
        :class:`api.NodeError` will be returned. Also note that this method not validate
        the IDs in any way - neither if they actually belong to an existing asset
        object nor if the user has adequate permissions.
        """
        primary_keys = set[str]()
        for asset_id in ids:
            type_name, *key = api.decode_key(asset_id)
            origin, _ = api.get_node_origin(type_name, info)

            # This check is crucial - we make sure that the ID is from some kind of
            # asset type. Since our inheritance is set up by using a foreign key to
            # the 'asset' table as the primary key of the child type, we know that any
            # primary key of the concrete asset type will also work on the parent.
            if not issubclass(origin, AssetNode) or not len(key) == 1:
                return api.NodeError(requested_id=asset_id)

            primary_keys.add(key[0])
        return primary_keys


@strawberry.input
class SetAssetVisibilityInput:
    ids: list[strawberry.ID] = strawberry.field(
        description="Asset IDs to update. IDs for assets that do not exist will"
        "silently be dropped, invalid IDs will return a `NodeError`."
    )
    visibility: AssetVisibility = strawberry.field(
        description="Visibility value that should be set for all assets."
    )


@strawberry.type
class SetAssetVisibilitySuccess:
    update_count: int


SetAssetVisibilityResult = strawberry.union(
    "SetAssetVisibilityResult", types=(SetAssetVisibilitySuccess, api.NodeError)
)


@api.schema.mutation
class Mutation:
    @strawberry.field(description="Set the visibility of one or more asset(s).")
    def set_asset_visibility(
        self, info: api.InfoType, input: SetAssetVisibilityInput
    ) -> SetAssetVisibilityResult:
        primary_keys = AssetNode.extract_primary_keys_from_ids(info, input.ids)
        if isinstance(primary_keys, api.NodeError):
            return primary_keys
        update_count = (
            Asset.objects.for_user(info.context.user, "libraries.change_asset")
            .filter(pk__in=primary_keys)
            .update(visibility=input.visibility.value)
        )
        return SetAssetVisibilitySuccess(update_count=update_count)
