import dataclasses
import enum
from typing import Optional

import strawberry
from django import forms

from tumpara import api
from tumpara.accounts.api import JoinableNode
from tumpara.accounts.models import User
from tumpara.libraries import storage
from tumpara.libraries.models import Library, Visibility


@strawberry.enum
class EffectiveVisibility(enum.Enum):
    PUBLIC = Visibility.PUBLIC
    INTERNAL = Visibility.INTERNAL
    MEMBERS = Visibility.MEMBERS
    OWNERS = Visibility.OWNERS


@api.remove_duplicate_node_interface
@strawberry.type(name="Library", description="A library containing media.")
class LibraryNode(
    JoinableNode, api.DjangoNode, fields=["source", "context", "default_visibility"]
):
    obj: strawberry.Private[Library]
    default_visibility: EffectiveVisibility = dataclasses.field(init=False)


@strawberry.type
class LibraryEdge(api.Edge[LibraryNode]):
    node: LibraryNode


@strawberry.type(description="A connection to a list of libraries.")
class LibraryConnection(
    api.DjangoConnection[LibraryNode, Library],
    name="library",
    pluralized_name="libraries",
):
    edges: list[Optional[LibraryEdge]]
    nodes: list[Optional[LibraryNode]]


@api.schema.query
class Query:
    libraries: Optional[LibraryConnection] = api.DjangoConnectionField(  # type: ignore
        description="All libraries that are available."
    )

    @strawberry.field(
        description="Check whether a given library source URI is valid. This query is "
        "only available for users that have the permission to create new libraries and "
        "will return `null` otherwise."
    )
    def check_library_source(self, info: api.InfoType, uri: str) -> Optional[bool]:
        if not info.context.user.has_perm("libraries.add_library"):
            return None
        try:
            storage.backends.build(uri).check()
            return True
        except:
            return False


class LibraryForm(forms.ModelForm[Library]):
    class Meta:
        model = Library
        fields = ["source", "default_visibility"]


class CreateLibraryForm(LibraryForm):
    class Meta(LibraryForm.Meta):
        fields = LibraryForm.Meta.fields + ["context"]


@strawberry.input(description="Create a new library.")
class CreateLibraryInput(api.CreateFormInput[CreateLibraryForm, LibraryNode]):
    default_visibility: EffectiveVisibility


@strawberry.input(description="Change an existing library.")
class UpdateLibraryInput(api.UpdateFormInput[LibraryForm, LibraryNode]):
    default_visibility: Optional[EffectiveVisibility]


LibraryMutationResult = strawberry.union(
    "LibraryMutationResult", (LibraryNode, api.FormError, api.NodeError)
)


@api.schema.mutation
class Mutation:
    @strawberry.field(
        description=CreateLibraryInput._type_definition.description,  # type: ignore
    )
    def create_library(
        self, info: api.InfoType, input: CreateLibraryInput
    ) -> Optional[LibraryMutationResult]:
        node = input.resolve(info)
        if not isinstance(node, LibraryNode):
            return node

        assert isinstance(info.context.user, User)
        node.obj.add_membership(info.context.user, owner=True)

        return node

    @strawberry.field(
        description=UpdateLibraryInput._type_definition.description,  # type: ignore
    )
    def update_library(
        self, info: api.InfoType, input: UpdateLibraryInput
    ) -> Optional[LibraryMutationResult]:
        return input.resolve(info)
