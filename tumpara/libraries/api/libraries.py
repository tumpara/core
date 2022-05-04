import enum
from typing import Optional

import strawberry
from django import forms

from tumpara import api
from tumpara.accounts.api import JoinableNode
from tumpara.accounts.models import User
from tumpara.libraries import storage
from tumpara.libraries.models import Library, Visibility


@api.remove_duplicate_node_interface
@strawberry.type(name="Library", description="A library containing media.")
class LibraryNode(
    JoinableNode,
    api.DjangoNode[Library],
    fields=["source", "context"],
):
    _obj: strawberry.Private[Library]


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


@strawberry.enum
class LibraryVisibility(enum.Enum):
    PUBLIC = Visibility.PUBLIC
    INTERNAL = Visibility.INTERNAL
    MEMBERS = Visibility.MEMBERS
    OWNERS = Visibility.OWNERS


class LibraryForm(forms.ModelForm[Library]):
    class Meta:
        model = Library
        fields = ["source", "default_visibility"]


class CreateLibraryForm(LibraryForm):
    class Meta(LibraryForm.Meta):
        fields = LibraryForm.Meta.fields + ["context"]


@strawberry.input(description="Create a new library.")
class CreateLibraryInput(api.CreateFormInput[CreateLibraryForm]):
    default_visibility: LibraryVisibility


@strawberry.input(description="Change an existing library.")
class UpdateLibraryInput(api.UpdateFormInput[LibraryForm]):
    default_visibility: Optional[LibraryVisibility]  # type: ignore


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
        form = input.prepare(info)
        if not isinstance(form, CreateLibraryForm):
            return form

        obj = form.save()
        assert isinstance(obj, Library)

        assert isinstance(info.context.user, User)
        obj.add_membership(info.context.user, owner=True)

        return LibraryNode(obj)

    @strawberry.field(
        description=UpdateLibraryInput._type_definition.description,  # type: ignore
    )
    def update_library(
        self, info: api.InfoType, input: UpdateLibraryInput
    ) -> Optional[LibraryMutationResult]:
        form = input.prepare(info)
        if not isinstance(form, LibraryForm):
            return form
        return LibraryNode(form.save())