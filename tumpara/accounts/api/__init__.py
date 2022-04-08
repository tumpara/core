from typing import Any, Optional, cast

import strawberry
from django.db import models

from tumpara import api
from tumpara.api import filtering, relay

from .. import models as accounts_models


@strawberry.input(description="Filtering options when querying `User` objects.")
class UserFilter:
    username: Optional[filtering.StringFilter] = None
    full_name: Optional[filtering.StringFilter] = None
    short_name: Optional[filtering.StringFilter] = None
    any_name: Optional[filtering.StringFilter] = strawberry.field(
        default=None, description="Filter based on any of the name fields."
    )
    is_active: Optional[bool] = None

    def build_query(self, field_name: str) -> models.Q:
        """Build a Django Q object for this filter.

        :param field_name: The name of the field where models should be filtered. When
            building a query for a top-level queryset of the correct type, set this to
            an empty string. When building a query for a related field, set this to the
            field's name.
        """
        prefix = field_name + "__" if field_name != "" else ""
        query = models.Q()

        if self.username is not None:
            query &= self.username.build_query(f"{prefix}username")
        if self.full_name is not None:
            query &= self.full_name.build_query(f"{prefix}full_name")
        if self.short_name is not None:
            query &= self.short_name.build_query(f"{prefix}short_name")
        if self.any_name is not None:
            query &= (
                self.any_name.build_query(f"{prefix}username")
                | self.any_name.build_query(f"{prefix}full_name")
                | self.any_name.build_query(f"{prefix}short_name")
            )
        if self.is_active is not None:
            query &= models.Q((f"{prefix}is_active", self.is_active))

        return query


@strawberry.type(description="A user with an account on this server.")
class User(
    relay.DjangoNode[accounts_models.User],
    fields=["username", "full_name", "short_name", "email", "is_active"],
):
    def __init__(self, *args: Any, **kwargs: Any):
        relay.DjangoNode.__init__(self, *args, **kwargs)

    @strawberry.field(description="Name to display for the user.")
    def display_name(self) -> str:
        if self._obj.short_name:
            return self._obj.short_name
        elif self._obj.full_name:
            return self._obj.full_name
        else:
            return self._obj.username


# We need to redefine 'node' and 'edges' below because otherwise Strawberry thinks they
# are still generic:
# https://github.com/strawberry-graphql/strawberry/issues/1195


@strawberry.type
class UserEdge(relay.Edge[User]):
    node: User


@strawberry.type(description="A connection to a list of users.")
class UserConnection(
    relay.DjangoConnection[User, accounts_models.User],
    name="user",
    pluralized_name="users",
):
    edges: list[Optional[UserEdge]]
    nodes: list[Optional[User]]


def resolve_user_connection(
    info: api.InfoType, filter: Optional[UserFilter] = None, **kwargs: Any
) -> Optional[UserConnection]:
    queryset = accounts_models.User.objects.all()
    if filter is not None:
        queryset = queryset.filter(filter.build_query(""))
    return UserConnection.from_queryset(queryset, info, **kwargs)


@strawberry.type
class Query:
    users: Optional[UserConnection] = relay.ConnectionField(  # type: ignore
        description="All users available on this server."
    )(resolve_user_connection)

    @strawberry.field(
        description="The user that is currently accessing the API. For anonymous "
        "sessions, this will be `null`."
    )
    def me(self, info: api.InfoType) -> Optional[User]:
        if info.context.user.is_authenticated:
            return User(info.context.user)
        else:
            return None
