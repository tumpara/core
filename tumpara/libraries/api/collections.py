from typing import Optional

import strawberry
from django import forms
from django.db import models

from tumpara import api
from tumpara.accounts.api import JoinableNode
from tumpara.accounts.models import User

from ..models import Collection
from .assets import AssetNode


@strawberry.input(description="Filtering options when querying `Collection` objects.")
class CollectionFilter:
    title: Optional[api.StringFilter] = None

    def build_query(self, info: api.InfoType, field_name: Optional[str]) -> models.Q:
        prefix = field_name + "__" if field_name else ""
        query = models.Q()

        if self.title is not None:
            query &= self.title.build_query(info, f"{prefix}title")

        return query


@api.remove_duplicate_node_interface
@strawberry.type(name="Collection")
class CollectionNode(JoinableNode, api.DjangoNode, fields=["title"]):
    obj: strawberry.Private[Collection]


@strawberry.type
class CollectionEdge(api.Edge[CollectionNode]):
    node: CollectionNode


@strawberry.type(description="A connection to a list of collections.")
class CollectionConnection(
    api.DjangoConnection[CollectionNode, Collection],
    name="collection",
    pluralized_name="collections",
):
    edges: list[Optional[CollectionEdge]]
    nodes: list[Optional[CollectionNode]]


@api.schema.query
class Query:
    collections: Optional[CollectionConnection] = api.DjangoConnectionField(  # type: ignore
        filter_type=CollectionFilter,
        description="All available collections.",
    )


class CollectionForm(forms.ModelForm[Collection]):
    class Meta:
        model = Collection
        fields = ["title"]


@strawberry.input(description="Create a new collection.")
class CreateCollectionInput(api.CreateFormInput[CollectionForm, CollectionNode]):
    pass


@strawberry.input(description="Change an existing collection.")
class UpdateCollectionInput(api.UpdateFormInput[CollectionForm, CollectionNode]):
    add_asset_ids: Optional[list[strawberry.ID]] = strawberry.field(
        default=None,
        description="ID of `Asset` items to add to the collection. Note that this is "
        "performed before removal, so if a node is present both here and in the other "
        "list, it will end up not present in the collection.",
    )
    remove_asset_ids: Optional[list[strawberry.ID]] = strawberry.field(
        default=None,
        description="ID of `Asset` items to remove from the collection. If an asset is "
        "not already in the collection, it will be silently skipped.",
    )


CollectionMutationResult = strawberry.union(
    "CollectionMutationResult", (CollectionNode, api.FormError, api.NodeError)
)


@api.schema.mutation
class Mutation:
    @strawberry.field(
        description=CreateCollectionInput._type_definition.description,  # type: ignore
    )
    def create_collection(
        self, info: api.InfoType, input: CreateCollectionInput
    ) -> Optional[CollectionMutationResult]:
        node = input.resolve(info)
        if not isinstance(node, CollectionNode):
            return node

        assert isinstance(info.context.user, User)
        node.obj.add_membership(info.context.user, owner=True)

        return node

    @strawberry.field(
        description=UpdateCollectionInput._type_definition.description,  # type: ignore
    )
    def update_collection(
        self, info: api.InfoType, input: UpdateCollectionInput
    ) -> Optional[CollectionMutationResult]:
        collection_node = input.resolve(info)
        if not isinstance(collection_node, CollectionNode):
            return collection_node

        if not input.add_asset_ids and not input.remove_asset_ids:
            return collection_node

        add_asset_nodes = list[AssetNode]()
        for asset_node_id in input.add_asset_ids or []:
            asset_node = api.resolve_node(
                info, asset_node_id, AssetNode, permission="libraries.view_asset"
            )
            if asset_node is None:
                return api.NodeError(requested_id=asset_node_id)
            add_asset_nodes.append(asset_node)

        remove_asset_nodes = list[AssetNode]()
        for asset_node_id in input.remove_asset_ids or []:
            asset_node = api.resolve_node(
                info, asset_node_id, AssetNode, permission="libraries.view_asset"
            )
            if asset_node is None:
                return api.NodeError(requested_id=asset_node_id)
            remove_asset_nodes.append(asset_node)

        collection = collection_node.obj
        collection.assets.add(*[node.obj for node in add_asset_nodes])
        collection.assets.remove(*[node.obj for node in remove_asset_nodes])

        return collection_node
