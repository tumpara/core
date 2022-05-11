from typing import Any, Optional, TypeVar

import strawberry
from django.contrib.contenttypes.models import ContentType
from django.db import models

from tumpara import api

from ..models import Joinable, JoinableQuerySet, User, UserMembership
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
        return self.node.obj._membership_is_owner  # type: ignore


@strawberry.type(description="A connection to a list of users.")
class UserMembershipConnection(
    api.DjangoConnection[UserNode, User],
    name="user",
    pluralized_name="users",
):
    edges: list[Optional[UserMembershipEdge]]
    nodes: list[Optional[UserNode]]


@strawberry.interface(name="Joinable")
class JoinableNode(api.DjangoNode, fields=[]):
    obj: strawberry.Private[Joinable]

    @api.DjangoConnectionField(
        UserMembershipConnection,
        description="Users that are a member and have permission to view.",
    )
    def members(self, info: api.InfoType, **kwargs: Any) -> models.QuerySet[User]:
        return (
            UserNode.get_queryset(info)
            .filter(
                membership__content_type=ContentType.objects.get_for_model(
                    self._get_model_type()
                ),
                membership__object_pk=self.obj.pk,
            )
            .annotate(_membership_is_owner=models.F("membership__is_owner"))
        )

    @classmethod
    def get_queryset(
        cls, info: api.InfoType, permission: Optional[str] = None
    ) -> JoinableQuerySet[Any]:
        model = cls._get_model_type()
        assert issubclass(model, Joinable)
        manager = model._default_manager
        if not issubclass(manager._queryset_class, JoinableQuerySet):  # type: ignore
            raise NotImplementedError
        resolved_permission = permission or build_permission_name(model, "view")
        return manager.for_user(info.context.user, resolved_permission)  # type: ignore
