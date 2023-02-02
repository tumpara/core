import dataclasses
import datetime
import enum
from collections.abc import Sequence, Set
from typing import Any, Optional, cast

import strawberry
from django.db import NotSupportedError, models

from tumpara import api
from tumpara.accounts.utils import build_permission_name

from ..models import Asset, AssetModel, AssetQuerySet, File, Visibility
from .libraries import EffectiveVisibility, LibraryNode

########################################################################################
# Files                                                                                #
########################################################################################


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


########################################################################################
# Visibility                                                                           #
########################################################################################


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
        description="Whether to include public assets, where the visibility has been "
        "inherited from the library. By default (or when set to `null`) this will take "
        "the same value as the `public` option.",
    )
    internal_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include internal assets, where the visibility has been "
        "inherited from the library. By default (or when set to `null`) this will take "
        "the same value as the `internal` option.",
    )
    members_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include assets visible only to library members, where "
        "the visibility has been inherited from the library. By default (or when set "
        "to `null`) this will take the same value as the `members` option.",
    )
    owners_from_library: Optional[bool] = strawberry.field(
        default=None,
        description="Whether to include assets visible only to library owners, where "
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


########################################################################################
# Filtering                                                                            #
########################################################################################


class AssetFilter:
    def build_query(
        self, info: api.InfoType, field_name: Optional[str]
    ) -> tuple[models.Q, dict[str, models.Expression | models.F]]:
        return models.Q(), {}

    def get_instance_types(self) -> Sequence[type[AssetModel]]:
        """List of instance types that should be passed to
        :meth:`AssetQuerySet.resolve_instances`."""
        return []


asset_filter_types = list[type[AssetFilter]]()


def register_asset_filter(
    filter_type: type[AssetFilter],
) -> type[AssetFilter]:
    prepped_type = api.schema.prep_type(filter_type, is_input=True)
    asset_filter_types.append(prepped_type)
    return prepped_type


@register_asset_filter
class MainAssetFilter(AssetFilter):
    media_timestamp: Optional[api.DateTimeFilter] = None
    visibility: Optional[AssetVisibilityFilter] = None
    use_stacks: bool = strawberry.field(
        default=True,
        description="Whether the result should adhere to asset stacking. If this is "
        "option is set to `true`, only one asset from each stack will be returned. "
        "This is ignored if `stacked_with` is set.\n\n"
        "Note that when using this option, assets in a stack that are not the "
        "representative will directly be filtered out. That means that a stack might "
        "not appear at all if its representative is either not visible to the current "
        "user or filtered out by other options.",
    )
    stacked_with: Optional[strawberry.ID] = strawberry.field(
        default=None,
        description="Filter by asset stacks. Set this to an ID of an Asset and the "
        "result will contain all the other assets stacked together with the provided "
        "one.",
    )

    def build_query(
        self, info: api.InfoType, field_name: Optional[str]
    ) -> tuple[models.Q, dict[str, models.Expression | models.F]]:
        prefix = field_name + "__" if field_name else ""
        query, aliases = super().build_query(info, field_name)

        if self.media_timestamp is not None:
            next_query, next_aliases = self.media_timestamp.build_query(
                info, f"{prefix}media_timestamp"
            )
            query &= next_query
            aliases |= next_aliases

        if self.visibility is not None:
            query &= self.visibility.build_query(
                info, f"{prefix}visibility", f"{prefix}library__default_visibility"
            )

        if (
            stacked_with_node := api.resolve_node(info, self.stacked_with, AssetNode)
        ) is not None:
            query &= models.Q(stack_key=stacked_with_node.obj.stack_key)

        if self.use_stacks and stacked_with_node is None:
            query &= models.Q(stack_key__isnull=True) | models.Q(
                stack_representative=True
            )

        return query, aliases


########################################################################################
# Object types                                                                         #
########################################################################################


@strawberry.interface(name="Asset")
class AssetNode(
    api.DjangoNode,
    fields=[
        "library",
        "visibility",
        "import_timestamp",
        "media_timestamp",
    ],
):
    obj: strawberry.Private[Asset]
    # The explicit fields here are to please MyPy:
    library: Optional[LibraryNode] = dataclasses.field(init=False)
    visibility: AssetVisibility = dataclasses.field(init=False)

    @strawberry.field(
        description="The effective `visibility` value, which might come from the "
        "library's settings."
    )
    def effective_visibility(self) -> EffectiveVisibility:
        # This is annotated by the for_user() method of the asset's manager.
        return cast(Any, self).obj.effective_visibility  # type: ignore[no-any-return]

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
        return (
            model._default_manager.for_user(info.context.user, resolved_permission)
            .resolve_instances()
            .order_by("media_timestamp")
        )

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


@strawberry.type
class AssetEdge(api.Edge[AssetNode]):
    node: AssetNode

    @strawberry.field()
    def decoded_cursor(self) -> str:
        return str(api.decode_key(self.cursor))


@strawberry.type(description="A connection to a list of assets.")
class AssetConnection(
    api.DjangoConnection[AssetNode, Asset],
    name="asset",
    pluralized_name="assets",
):
    edges: list[Optional[AssetEdge]]
    nodes: list[Optional[AssetNode]]

    @classmethod
    def create_node(cls, obj: models.Model) -> AssetNode:
        from tumpara.photos.api import PhotoNode
        from tumpara.photos.models import Photo

        from ..models import Note
        from .notes import NoteNode

        # TODO This should probably be refactored into some sort of registration
        #  pattern.
        if isinstance(obj, Note):
            return NoteNode(obj=obj)
        elif isinstance(obj, Photo):
            return PhotoNode(obj=obj)
        else:
            raise TypeError(f"unsupported asset type: {type(obj)}")

    @classmethod
    def from_queryset(
        cls,
        queryset: models.QuerySet[Asset],
        info: api.InfoType,
        *,
        after: Optional[str] = None,
        before: Optional[str] = None,
        first: Optional[int] = None,
        last: Optional[int] = None,
    ) -> "AssetConnection":
        try:
            after_timestamp = datetime.datetime.fromisoformat(after)
        except (TypeError, ValueError):
            pass
        else:
            skip_count = queryset.filter(media_timestamp__lte=after_timestamp).count()
            after = api.encode_key("Connection", skip_count - 1)

        try:
            before_timestamp = datetime.datetime.fromisoformat(before)
        except (TypeError, ValueError):
            pass
        else:
            # Note the < comparison here instead of <= in the first case.
            skip_count = queryset.filter(media_timestamp__lt=before_timestamp).count()
            before = api.encode_key("Connection", skip_count)

        return super().from_queryset(
            queryset,
            info,
            after=after,
            before=before,
            first=first,
            last=last,
        )


########################################################################################
# Mutations                                                                            #
########################################################################################


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


@strawberry.input
class StackingMutationInput:
    ids: list[strawberry.ID] = strawberry.field(
        description="Asset IDs to update. IDs for assets that do not exist will "
        "silently be dropped, invalid IDs will return a `NodeError`."
    )


@strawberry.type
class StackingMutationSuccess:
    stack_size: int = strawberry.field(description="Size of the stack.")


StackingMutationResult = strawberry.union(
    "StackingMutationResult", types=(StackingMutationSuccess, api.NodeError)
)


@strawberry.type
class SetStackRepresentativeSuccess:
    representative: AssetNode = strawberry.field(
        description="The new representative of the stack."
    )


SetStackRepresentativeResult = strawberry.union(
    "SetStackRepresentativeResult", types=(SetStackRepresentativeSuccess, api.NodeError)
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

    @strawberry.field(description="Stack the given set of assets together.")
    def stack_assets(
        self, info: api.InfoType, input: StackingMutationInput
    ) -> StackingMutationResult:
        primary_keys = AssetNode.extract_primary_keys_from_ids(info, input.ids)
        if isinstance(primary_keys, api.NodeError):
            return primary_keys
        stack_size = (
            Asset.objects.for_user(info.context.user, "libraries.change_asset")
            .filter(pk__in=primary_keys)
            .stack()
        )
        return StackingMutationSuccess(stack_size=stack_size)

    @strawberry.field(description="Clear the stack of each of the given assets.")
    def unstack_assets(
        self, info: api.InfoType, input: StackingMutationInput
    ) -> StackingMutationResult:
        primary_keys = AssetNode.extract_primary_keys_from_ids(info, input.ids)
        if isinstance(primary_keys, api.NodeError):
            return primary_keys
        stack_size = (
            Asset.objects.for_user(info.context.user, "libraries.change_asset")
            .filter(pk__in=primary_keys)
            .unstack()
        )
        return StackingMutationSuccess(stack_size=stack_size)

    @strawberry.field(
        description="Make the given asset the representative of its stack."
    )
    def set_stack_representative(
        self, info: api.InfoType, id: strawberry.ID
    ) -> SetStackRepresentativeResult:
        node = api.resolve_node(
            info, id, AssetNode, permission="libraries.change_asset"
        )
        if node is None:
            return api.NodeError(requested_id=id)
        try:
            node.obj.represent_stack()
        except NotSupportedError:
            return api.NodeError(requested_id=id)
        return SetStackRepresentativeSuccess(representative=node)
