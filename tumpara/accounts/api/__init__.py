from typing import Any, Optional, cast

import graphql
import strawberry
from django.db import models
from strawberry.arguments import UNSET

from tumpara.api import filtering, relay

from .. import models as accounts_models


@strawberry.input(description="Filtering options when querying `User` objects.")
class UserFilter:
    login_name: Optional[filtering.StringFilter]
    full_name: Optional[filtering.StringFilter]
    short_name: Optional[filtering.StringFilter]
    any_name: Optional[filtering.StringFilter] = strawberry.field(
        description="Filter based on any of the name fields."
    )
    is_active: Optional[bool]

    def build_query(self, field_name: str) -> models.Q:
        """Build a Django Q object for this filter.

        :param field_name: The name of the field where models should be filtered. When
            building a query for a top-level queryset of the correct type, set this to
            an empty string. When building a query for a related field, set this to the
            field's name.
        """
        prefix = field_name + "__" if field_name != "" else ""
        query = models.Q()

        if self.login_name is not None:
            query &= self.login_name.build_query(f"{prefix}login_name")
        if self.full_name is not None:
            query &= self.full_name.build_query(f"{prefix}full_name")
        if self.short_name is not None:
            query &= self.short_name.build_query(f"{prefix}short_name")
        if self.any_name is not None:
            query &= (
                self.any_name.build_query(f"{prefix}login_name")
                | self.any_name.build_query(f"{prefix}full_name")
                | self.any_name.build_query(f"{prefix}short_name")
            )
        if self.is_active is not None:
            query &= models.Q((f"{prefix}is_active", self.is_active))

        return query


@strawberry.type(description="A user with an account on this server.")
class User(relay.Node):
    login_name: str = strawberry.field(
        description=str(accounts_models.User._meta.get_field("login_name").help_text)
    )
    full_name: str = strawberry.field(
        description=str(accounts_models.User._meta.get_field("full_name").help_text)
    )
    short_name: str = strawberry.field(
        description=str(accounts_models.User._meta.get_field("short_name").help_text)
    )
    email: str = strawberry.field(
        description=str(accounts_models.User._meta.get_field("email").help_text)
    )
    is_active: bool = strawberry.field(
        description=str(accounts_models.User._meta.get_field("is_active").help_text)
    )

    @classmethod
    def is_type_of(cls, obj: Any, info: graphql.GraphQLResolveInfo) -> bool:
        return isinstance(obj, accounts_models.User)

    @classmethod
    def get_node_from_key(cls, info: graphql.GraphQLResolveInfo, *key: str) -> Any:
        assert len(key) == 1, "invalid key format"
        return accounts_models.User.objects.get(pk=key[0])


# We need to redefine 'node' and 'edges' below because otherwise Strawberry thinks they
# are still generic:
# https://github.com/strawberry-graphql/strawberry/issues/1195


@strawberry.type
class UserEdge(relay.Edge[User]):
    node: User = strawberry.field(description="The user object connected to this edge.")


@strawberry.type(description="A connection to a list of users.")
class UserConnection(relay.Connection[User], name="user", pluralized_name="users"):
    edges: list[Optional[UserEdge]]
    nodes: list[Optional[User]]


def resolve_user_connection(
    filter: Optional[UserFilter] = UNSET, **kwargs: Any
) -> Optional[UserConnection]:
    queryset = accounts_models.User.objects.all()
    if filter not in (None, UNSET):
        queryset.filter(filter.build_query(""))
    return UserConnection.from_sequence(queryset, queryset.count(), **kwargs)


@strawberry.type
class Query:
    @strawberry.field(description="Resolve a node by its ID.")
    def node(
        root: Any, info: graphql.GraphQLResolveInfo, id: strawberry.ID
    ) -> Optional[relay.Node]:
        type_name, *key = relay.decode_key(str(id))
        origin, _ = relay.get_node_origin(type_name, info)
        node = origin.get_node_from_key(info, *key)

        if hasattr(origin, "is_type_of"):
            assert origin.is_type_of(node, info), (  # type: ignore
                "get_node_from_key() must return an object that is compatible with "
                "is_type_of() "
            )

        return cast(relay.Node, node)

    users: Optional[UserConnection] = relay.ConnectionField(
        description="All users available on this server."
    )(resolve_user_connection)
