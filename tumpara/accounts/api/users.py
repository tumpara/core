from typing import Optional

import strawberry
from django.db import models

from tumpara import api

from ..models import User
from ..utils import build_permission_name


@strawberry.input(description="Filtering options when querying `User` objects.")
class UserFilter:
    username: Optional[api.StringFilter] = None
    full_name: Optional[api.StringFilter] = None
    short_name: Optional[api.StringFilter] = None
    any_name: Optional[api.StringFilter] = strawberry.field(
        default=None, description="Filter based on any of the name fields."
    )
    is_active: Optional[bool] = None

    def build_query(self, field_name: Optional[str]) -> models.Q:
        prefix = field_name + "__" if field_name else ""
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


@strawberry.type(name="User", description="A user with an account on this server.")
class UserNode(
    api.DjangoNode[User],
    fields=["username", "full_name", "short_name", "email", "is_active"],
):
    username: str
    short_name: str
    full_name: str

    def __init__(self, _obj: User):
        self._obj = _obj

    @strawberry.field(description="Name to display for the user.")
    def display_name(self) -> str:
        if self.short_name:
            return self.short_name
        elif self.full_name:
            return self.full_name
        else:
            return self.username

    @classmethod
    def get_queryset(
        cls, info: api.InfoType, permission: Optional[str] = None
    ) -> models.QuerySet[User]:
        resolved_permission = permission or build_permission_name(
            cls._get_model_type(), "view"
        )
        return User.objects.for_user(info.context.user, resolved_permission)


# We need to redefine 'node' and 'edges' below because otherwise Strawberry thinks they
# are still generic:
# https://github.com/strawberry-graphql/strawberry/issues/1195


@strawberry.type
class UserEdge(api.Edge[UserNode]):
    node: UserNode


@strawberry.type(description="A connection to a list of users.")
class UserConnection(
    api.DjangoConnection[UserNode, User],
    name="user",
    pluralized_name="users",
):
    edges: list[Optional[UserEdge]]
    nodes: list[Optional[UserNode]]
