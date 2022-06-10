from collections.abc import Sequence
from typing import Optional

import strawberry
from django.db import NotSupportedError, models

from tumpara import api
from tumpara.libraries.api import AssetNode, AssetVisibilityFilter

from ..models import GalleryAssetQuerySet  # noqa: F401
from ..models import GalleryAsset, GalleryAssetModel


class GalleryAssetFilter:
    def build_query(
        self, info: api.InfoType, field_name: Optional[str]
    ) -> tuple[models.Q, dict[str, models.Expression | models.F]]:
        return models.Q(), {}

    def get_instance_types(self) -> Sequence[type[GalleryAssetModel]]:
        """List of instance types that should be passed to
        :meth:`GalleryAssetQuerySet.resolve_instances`"""
        return []


gallery_asset_filter_types = list[type[GalleryAssetFilter]]()


def register_gallery_asset_filter(
    filter_type: type[GalleryAssetFilter],
) -> type[GalleryAssetFilter]:
    prepped_type = api.schema.prep_type(filter_type, is_input=True)
    gallery_asset_filter_types.append(prepped_type)
    return prepped_type


@register_gallery_asset_filter
class MainGalleryAssetFilter(GalleryAssetFilter):
    media_timestamp: Optional[api.DateTimeFilter] = None
    visibility: Optional[AssetVisibilityFilter] = None
    use_stacks: bool = strawberry.field(
        default=True,
        description="Whether to use stacks. If this is `true`, only one asset is "
        "returned per stack. Assets not in any stack are returned as well.\n\n"
        "Note that when using this option, assets in a stack that are not the "
        "representative will directly be filtered out. That means that a stack might "
        "not appear at all if its representative is either not visible to the current "
        "user or filtered out by other options.",
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

        if self.use_stacks:
            query &= models.Q(stack_key__isnull=True) | models.Q(
                stack_representative=True
            )

        return query, aliases


@api.remove_duplicate_node_interface
@strawberry.interface(name="GalleryAsset")
class GalleryAssetNode(AssetNode, api.DjangoNode, fields=["media_timestamp"]):
    obj: strawberry.Private[GalleryAsset]


@strawberry.type
class GalleryAssetEdge(api.Edge[GalleryAssetNode]):
    node: GalleryAssetNode


@strawberry.type(description="A connection to a list of gallery assets.")
class GalleryAssetConnection(
    api.DjangoConnection[GalleryAssetNode, GalleryAsset],
    name="gallery asset",
    pluralized_name="gallery assets",
):
    edges: list[Optional[GalleryAssetEdge]]
    nodes: list[Optional[GalleryAssetNode]]

    @classmethod
    def create_node(cls, obj: models.Model) -> GalleryAssetNode:
        from tumpara.photos.api import PhotoNode
        from tumpara.photos.models import Photo

        from ..models import Note
        from .notes import NoteNode

        # TODO This should probably be refactored into some sort of registration
        #  pattern.
        if isinstance(obj, Note):
            return NoteNode(obj)
        elif isinstance(obj, Photo):
            return PhotoNode(obj)
        else:
            raise TypeError(f"unsupported gallery asset type: {type(obj)}")


@strawberry.input
class StackingMutationInput:
    ids: list[strawberry.ID] = strawberry.field(
        description="Gallery asset IDs to update. IDs for assets that do not exist "
        "will silently be dropped, invalid IDs will return a `NodeError`."
    )


@strawberry.type
class StackingMutationSuccess:
    stack_size: int = strawberry.field(description="Size of the stack.")


StackingMutationResult = strawberry.union(
    "StackingMutationResult", types=(StackingMutationSuccess, api.NodeError)
)


@strawberry.type
class SetStackRepresentativeSuccess:
    representative: GalleryAssetNode = strawberry.field(
        description="The new representative of the stack."
    )


SetStackRepresentativeResult = strawberry.union(
    "SetStackRepresentativeResult", types=(SetStackRepresentativeSuccess, api.NodeError)
)


@api.schema.mutation
class Mutation:
    @strawberry.field(description="Stack the given set of gallery assets together.")
    def stack_gallery_assets(
        self, info: api.InfoType, input: StackingMutationInput
    ) -> StackingMutationResult:
        primary_keys = GalleryAssetNode.extract_primary_keys_from_ids(info, input.ids)
        if isinstance(primary_keys, api.NodeError):
            return primary_keys
        stack_size = (
            GalleryAsset.objects.for_user(
                info.context.user, "gallery.change_galleryasset"
            )
            .filter(pk__in=primary_keys)
            .stack()
        )
        return StackingMutationSuccess(stack_size=stack_size)

    @strawberry.field(
        description="Clear the stack of each of the given gallery assets."
    )
    def unstack_gallery_assets(
        self, info: api.InfoType, input: StackingMutationInput
    ) -> StackingMutationResult:
        primary_keys = GalleryAssetNode.extract_primary_keys_from_ids(info, input.ids)
        if isinstance(primary_keys, api.NodeError):
            return primary_keys
        stack_size = (
            GalleryAsset.objects.for_user(
                info.context.user, "gallery.change_galleryasset"
            )
            .filter(pk__in=primary_keys)
            .unstack()
        )
        return StackingMutationSuccess(stack_size=stack_size)

    @strawberry.field(
        description="Make the given entry the representative of its stack."
    )
    def set_stack_representative(
        self, info: api.InfoType, id: strawberry.ID
    ) -> SetStackRepresentativeResult:
        node = api.resolve_node(info, id, "gallery.change_galleryasset")
        if not isinstance(node, GalleryAssetNode):
            return api.NodeError(requested_id=id)
        try:
            node.obj.represent_stack()
        except NotSupportedError:
            return api.NodeError(requested_id=id)
        return SetStackRepresentativeSuccess(representative=node)
