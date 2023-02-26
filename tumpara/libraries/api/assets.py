import collections
import dataclasses
import datetime
import enum
import math
from collections.abc import Sequence, Set
from typing import Annotated, Any, Optional, cast

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


@strawberry.type(
    description="An asset connection bucket is a subdivision of the entire asset "
    "dataset, pointing to some part in the middle. These objects are used to aid "
    "pagination from arbitrary points."
)
class AssetConnectionChunk:
    after_cursor: str = strawberry.field(
        description="Cursor to use as the `after` parameter for requesting this bucket."
    )
    before_cursor: str = strawberry.field(
        description="Cursor to use as the `before` parameter for requesting this "
        "bucket."
    )
    start_timestamp: datetime.datetime = strawberry.field(
        description="Media timestamp of the first asset in this bucket."
    )
    end_timestamp: datetime.datetime = strawberry.field(
        description="Media timestamp of the last asset in this bucket."
    )
    size: int = strawberry.field(description="The number of assets in this bucket.")


@strawberry.type(description="A connection to a list of assets.")
class AssetConnection(
    api.DjangoConnection[AssetNode, Asset],
    name="asset",
    pluralized_name="assets",
):
    edges: list[Optional[AssetEdge]]
    nodes: list[Optional[AssetNode]]
    queryset: strawberry.Private[AssetQuerySet[Asset]]

    @strawberry.field(
        description="Divide the entire dataset into easily paginateable chunks. This "
        "respects the `before` and `after` options, but `first` and `last` are "
        "ignored. Instead, you will always receive *all* chunks that are available."
    )
    def time_chunks(
        self,
        target_chunk_size: Annotated[
            int,
            strawberry.argument(
                name="targetSize",
                description="The returned chunks will contain about this number of "
                "assets. Any single chunk is guaranteed to be at most 1.5 times this "
                "size. Most chunks will be at least 0.5 times this size.",
            ),
        ] = 200,
    ) -> list[AssetConnectionChunk]:
        chunk_size_allowance = 0.5 * target_chunk_size
        minimum_chunk_size = math.ceil(target_chunk_size - chunk_size_allowance)
        maximum_chunk_size = math.floor(target_chunk_size + chunk_size_allowance)

        all_timestamps: list[datetime.datetime] = [
            cast(datetime.datetime, item[0])
            for item in Asset.objects.all()
            .resolve_instances(False)
            .order_by("media_timestamp")
            .values_list("media_timestamp")
        ]

        if len(all_timestamps) == 0:
            return []

        # For each asset, calculate the timestamp difference (in seconds) to the
        # previous one.
        timestamp_deltas = [
            0
            if index == 0
            else (all_timestamps[index] - all_timestamps[index - 1]).total_seconds()
            for index in range(len(all_timestamps))
        ]

        # Now calculate the average timestamp delta "around" each asset. This basically
        # measures how close assets are placed together, which we can later use to judge
        # if a gap in time is actually a big gap where it might be worth splitting.
        # In essence, the following invariant should hold:
        #   average_timestamp_deltas[i] = sum(
        #     timestamp_deltas[i ± target_chunk_size]
        #   ) / (2 * target_chunk_size + 1)
        # for every i. Or, in actual Python:
        #   average_timestamp_deltas[i] == sum(
        #     timestamp_deltas[i - maximum_chunk_size : i + maximum_chunk_size + 1]
        #   ) / (2 * maximum_chunk_size + 1)
        # The following window algorithm calculates the array in O(n), as apposed to the
        # brute force O(maximum_chunk_size * n) approach.
        average_timestamp_deltas = list[float]()
        current_deltas = collections.deque(timestamp_deltas[:maximum_chunk_size])
        current_delta_sum = sum(current_deltas)
        for index, timestamp_delta in enumerate(timestamp_deltas[maximum_chunk_size:]):
            current_deltas.append(timestamp_delta)
            current_delta_sum += timestamp_delta
            # Add 1 here because we want the average to be centered on the current
            # index:
            if len(current_deltas) > maximum_chunk_size + chunk_size_allowance + 1:
                current_delta_sum -= current_deltas.popleft()
            average_timestamp_deltas.append(current_delta_sum / len(current_deltas))
        while len(average_timestamp_deltas) < len(all_timestamps):
            current_delta_sum -= current_deltas.popleft()
            try:
                average_timestamp_deltas.append(current_delta_sum / len(current_deltas))
            except ZeroDivisionError:
                # This happens when there is only one asset.
                average_timestamp_deltas.append(0)

        max_timestamp_delta = max(timestamp_deltas)
        results = list[AssetConnectionChunk]()

        # The following greedy algorithm finds assets before which to split the dataset
        # into a new chunk. For each index, we calculate a badness score that currently
        # consists of the following two:
        # - How close the asset is to its predecessor, in relation to how close assets
        #   are to each in general. This is where the surrounding time delta average
        #   comes in – some users might sporadically take a few pictures and other might
        #   generate content in phases. For example, people might take more photos on
        #   vacation than when they are at home. Then we would like these vacations to
        #   be in single chunks as much as possible.
        # - Splits that produce evenly sized chunks are deemed less bad. This lets us
        #   somewhat adhere to the target chunk size.
        last_split_index = 0
        while (
            remaining_count := len(all_timestamps) - last_split_index
        ) > maximum_chunk_size:
            candidate_index = -1
            candidate_badness = math.inf

            for index in range(
                last_split_index + minimum_chunk_size,
                last_split_index + maximum_chunk_size,
            ):
                try:
                    # Timestamp deltas that are larger than the surrounding average
                    # are the ones we want here - this encourages splitting at places
                    # where the time jumps - for example when no new photos are taken
                    # for a few days. Note that using the median instead of the
                    # average would probably be better here.
                    timestamp_delta_badness = (
                        average_timestamp_deltas[index] / timestamp_deltas[index]
                    )
                except ZeroDivisionError:
                    # Since timestamps don't match, go for something large, but not
                    # infinity so that the chunk size can still have the last word in
                    # an edge case. Note that a value of "1" for this badness score
                    # would mean that this asset is averagely spaced to its neighbor.
                    timestamp_delta_badness = max_timestamp_delta

                # Prioritize chunks that are abound the target size.
                chunk_size_badness = (
                    abs((index - last_split_index) - target_chunk_size)
                    / chunk_size_allowance
                )

                badness = timestamp_delta_badness + chunk_size_badness
                if badness < candidate_badness:
                    candidate_index = index
                    candidate_badness = badness

            # Create a new chunk that contains assets from last_split_index
            # to candidate_index - 1 (both inclusive).
            results.append(
                AssetConnectionChunk(
                    after_cursor=api.encode_key("Connection", last_split_index - 1),
                    before_cursor=api.encode_key("Connection", candidate_index),
                    start_timestamp=all_timestamps[last_split_index],
                    end_timestamp=all_timestamps[candidate_index - 1],
                    size=candidate_index - last_split_index,
                )
            )
            last_split_index = candidate_index

        # Add the final chunk to the result as well. This goes from last_split_index to
        # len(all_timestamps) - 1 (both inclusive).
        results.append(
            AssetConnectionChunk(
                after_cursor=api.encode_key("Connection", last_split_index - 1),
                before_cursor=api.encode_key("Connection", len(all_timestamps)),
                start_timestamp=all_timestamps[last_split_index],
                end_timestamp=all_timestamps[len(all_timestamps) - 1],
                size=remaining_count,
            )
        )

        return results

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
