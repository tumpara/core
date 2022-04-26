import enum
from typing import Any, Optional

import strawberry
from django import forms

from tumpara import api
from tumpara.accounts import models as accounts_models
from tumpara.libraries import models as libraries_models
from tumpara.libraries import storage


@strawberry.type(name="Library", description="A library containing media.")
class LibraryNode(
    api.DjangoNode[libraries_models.Library],
    fields=["source", "context"],
):
    _obj: strawberry.Private[libraries_models.Library]


@strawberry.type
class LibraryEdge(api.Edge[LibraryNode]):
    node: LibraryNode


@strawberry.type(description="A connection to a list of libraries.")
class LibraryConnection(
    api.DjangoConnection[LibraryNode, libraries_models.Library],
    name="library",
    pluralized_name="libraries",
):
    edges: list[Optional[LibraryEdge]]
    nodes: list[Optional[LibraryNode]]


def resolve_libraries_connection(
    info: api.InfoType, **kwargs: Any
) -> Optional[LibraryConnection]:
    queryset = libraries_models.Library.objects.for_user(
        "libraries.view_library", info.context.user
    )
    return LibraryConnection.from_queryset(queryset, info, **kwargs)  # type: ignore


@strawberry.type
class Query:
    libraries = api.ConnectionField(description="All libraries that are available.")(
        resolve_libraries_connection
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
    PUBLIC = libraries_models.Visibility.PUBLIC
    INTERNAL = libraries_models.Visibility.INTERNAL
    MEMBERS = libraries_models.Visibility.MEMBERS
    OWNERS = libraries_models.Visibility.OWNERS


class LibraryForm(forms.ModelForm[libraries_models.Library]):
    class Meta:
        model = libraries_models.Library
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


@strawberry.type
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
        assert isinstance(obj, libraries_models.Library)

        assert isinstance(info.context.user, accounts_models.User)
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
