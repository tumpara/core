from typing import Any, Optional, TypeVar

import strawberry
from django.contrib.contenttypes import models as contenttypes_models
from django.db import models

from tumpara import api

from ..models import Joinable, JoinableQueryset, User, UserMembership
from ..utils import build_permission_name
from .users import UserNode

_Joinable = TypeVar("_Joinable", bound="Joinable")


@strawberry.type
class UserMembershipEdge(api.Edge[UserNode]):
    node: UserNode

    @strawberry.field(description=api.get_field_description(UserMembership, "is_owner"))
    def owner(self) -> bool:
        # Here, we expect the object to be annotated from the queryset built by members
        # field in JoinableNode.
        return self.node._obj._membership_is_owner  # type: ignore


@strawberry.type(description="A connection to a list of users.")
class UserMembershipConnection(
    api.DjangoConnection[UserNode, User],
    name="user",
    pluralized_name="users",
):
    edges: list[Optional[UserMembershipEdge]]
    nodes: list[Optional[UserNode]]


@strawberry.interface(name="Joinable")
class JoinableNode(api.DjangoNode[Joinable], fields=[]):
    @api.DjangoConnectionField(
        UserMembershipConnection,
        description="Users that are a member and have permission to view.",
    )
    def members(self, info: api.InfoType, **kwargs: Any) -> models.QuerySet[User]:
        return (
            UserNode.get_queryset(info)
            .filter(
                membership__content_type=contenttypes_models.ContentType.objects.get_for_model(
                    self._get_model_type()
                ),
                membership__object_pk=self._obj.pk,
            )
            .annotate(_membership_is_owner=models.F("membership__is_owner"))
        )

    @classmethod
    def get_queryset(cls, info: api.InfoType) -> models.QuerySet[_Joinable]:
        manager = cls._get_model_type()._default_manager
        if not issubclass(
            manager._queryset_class,  # type: ignore
            JoinableQueryset,
        ):
            raise NotImplementedError
        return manager.for_user(  # type: ignore
            build_permission_name(cls._get_model_type(), "view"),
            info.context.user,
        )
