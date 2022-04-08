from typing import Any, Optional

import strawberry
from django import forms

from tumpara import api
from tumpara.api import relay
from tumpara.libraries import models as libraries_models
from tumpara.libraries import storage


@strawberry.type(description="A library containing media.")
class Library(relay.Node):
    @classmethod
    def is_type_of(cls, obj: Any, info: api.InfoType) -> bool:
        return isinstance(obj, libraries_models.Library)

    @classmethod
    def get_node_from_key(cls, info: api.InfoType, *key: str) -> Any:
        assert len(key) == 1, "invalid key format"
        return libraries_models.Library.objects.get(pk=key[0])


@strawberry.type
class LibraryEdge(relay.Edge[Library]):
    node: Library = strawberry.field(
        description="The library object connected to this edge."
    )


@strawberry.type(description="A connection to a list of libraries.")
class LibraryConnection(
    relay.DjangoConnection[Library, libraries_models.Library],
    name="library",
    pluralized_name="libraries",
):
    edges: list[Optional[LibraryEdge]]
    nodes: list[Optional[Library]]


def resolve_libraries_connection(
    info: api.InfoType, **kwargs: Any
) -> Optional[LibraryConnection]:
    queryset = libraries_models.Library.objects.for_user(
        "libraries.view_library", info.context.user
    )
    return LibraryConnection.from_queryset(queryset, info, **kwargs)


@strawberry.type
class Query:
    libraries = relay.ConnectionField(  # type: ignore
        description="All libraries that are available."
    )(resolve_libraries_connection)

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


class CreateLibraryForm(forms.ModelForm):
    class Meta:
        model = libraries_models.Library
        fields = ["source", "default_visibility"]


@strawberry.input
class CreateLibraryInput:
    source: str


@strawberry.type
class Mutation:
    @strawberry.field(description="Create a new library")
    def manage_library(
        self,
        info: api.InfoType,
        id: Optional[strawberry.ID],
    ):
        pass
