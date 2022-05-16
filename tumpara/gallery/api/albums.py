from typing import Optional

import strawberry
from django import forms
from django.db import models

from tumpara import api
from tumpara.accounts.api import JoinableNode
from tumpara.accounts.models import User

from ..models import Album
from .gallery_assets import GalleryAssetNode


@strawberry.input(description="Filtering options when querying `Album` objects.")
class AlbumFilter:
    title: Optional[api.StringFilter] = None

    def build_query(self, info: api.InfoType, field_name: Optional[str]) -> models.Q:
        prefix = field_name + "__" if field_name else ""
        query = models.Q()

        if self.title is not None:
            query &= self.username.build_query(info, f"{prefix}title")

        return query


@api.remove_duplicate_node_interface
@strawberry.type(name="Album")
class AlbumNode(JoinableNode, api.DjangoNode, fields=["title"]):
    obj: strawberry.Private[Album]


@strawberry.type
class AlbumEdge(api.Edge[AlbumNode]):
    node: AlbumNode


@strawberry.type(description="A connection to a list of albums.")
class AlbumConnection(
    api.DjangoConnection[AlbumNode, Album],
    name="album",
    pluralized_name="albums",
):
    edges: list[Optional[AlbumEdge]]
    nodes: list[Optional[AlbumNode]]


@api.schema.query
class Query:
    albums: Optional[AlbumConnection] = api.DjangoConnectionField(  # type: ignore
        filter_type=AlbumFilter,
        description="All available gallery albums.",
    )


class AlbumForm(forms.ModelForm[Album]):
    class Meta:
        model = Album
        fields = ["title"]


@strawberry.input(description="Create a new gallery album.")
class CreateAlbumInput(api.CreateFormInput[AlbumForm, AlbumNode]):
    pass


@strawberry.input(description="Change an existing gallery album.")
class UpdateAlbumInput(api.UpdateFormInput[AlbumForm, AlbumNode]):
    add_asset_ids: Optional[list[strawberry.ID]] = strawberry.field(
        default=None,
        description="ID of `GalleryAsset` items to add to the album. Note that this is "
        "performed before removal, so if a node is present both here and in the other "
        "list, it will end up not present in the album.",
    )
    remove_asset_ids: Optional[list[strawberry.ID]] = strawberry.field(
        default=None,
        description="ID of `GalleryAsset` items to remove from the album. If an asset "
        "is not already in the album, it will be silently skipped.",
    )


AlbumMutationResult = strawberry.union(
    "AlbumMutationResult", (AlbumNode, api.FormError, api.NodeError)
)


@api.schema.mutation
class Mutation:
    @strawberry.field(
        description=CreateAlbumInput._type_definition.description,  # type: ignore
    )
    def create_album(
        self, info: api.InfoType, input: CreateAlbumInput
    ) -> Optional[AlbumMutationResult]:
        node = input.resolve(info)
        if not isinstance(node, AlbumNode):
            return node

        assert isinstance(info.context.user, User)
        node.obj.add_membership(info.context.user, owner=True)

        return node

    @strawberry.field(
        description=UpdateAlbumInput._type_definition.description,  # type: ignore
    )
    def update_album(
        self, info: api.InfoType, input: UpdateAlbumInput
    ) -> Optional[AlbumMutationResult]:
        album_node = input.resolve(info)
        if not isinstance(album_node, AlbumNode):
            return album_node

        if not input.add_asset_ids and not input.remove_asset_ids:
            return album_node

        add_asset_nodes = list[GalleryAssetNode]()
        for asset_node_id in input.add_asset_ids or []:
            asset = api.resolve_node(info, asset_node_id, "gallery.view_galleryasset")
            if asset is None:
                return api.NodeError(requested_id=asset_node_id)
            add_asset_nodes.append(asset)

        remove_asset_nodes = list[GalleryAssetNode]()
        for asset_node_id in input.remove_asset_ids or []:
            asset = api.resolve_node(info, asset_node_id, "gallery.view_galleryasset")
            if asset is None:
                return api.NodeError(requested_id=asset_node_id)
            remove_asset_nodes.append(asset)

        album = album_node.obj
        album.assets.add(*[node.obj for node in add_asset_nodes])
        album.assets.remove(*[node.obj for node in remove_asset_nodes])

        return album_node
