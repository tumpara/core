from typing import Any, Generic, Optional, TypeVar

import strawberry
from django.contrib.contenttypes import models as contenttypes_models
from django.db import models

from tumpara import api

from .. import models as accounts_models
from ..utils import build_permission_name
from .users import UserNode

_Joinable = TypeVar("_Joinable", bound="accounts_models.Joinable")


@strawberry.type
class UserMembershipEdge(api.Edge[UserNode]):
    node: UserNode

    @strawberry.field(
        description=api.get_field_description(
            accounts_models.UserMembership, "is_owner"
        )
    )
    def owner(self) -> bool:
        # Here, we expect the object to be annotated from the queryset built by members
        # field in JoinableNode.
        return self.node._obj._membership_is_owner


@strawberry.type(description="A connection to a list of users.")
class UserMembershipConnection(
    api.DjangoConnection[UserNode, accounts_models.User],
    name="user",
    pluralized_name="users",
):
    edges: list[Optional[UserMembershipEdge]]
    nodes: list[Optional[UserNode]]


@strawberry.interface
class JoinableNode(Generic[_Joinable], api.DjangoNode[_Joinable]):
    @api.DjangoConnectionField(
        UserMembershipConnection,
        description="Users that are a member and have permission to view.",
    )
    def members(
        self, info: api.InfoType, **kwargs: Any
    ) -> models.QuerySet[accounts_models.User]:
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
        if not issubclass(manager._queryset_class, accounts_models.JoinableQueryset):
            raise NotImplementedError
        return manager.for_user(
            build_permission_name(cls._get_model_type(), "view"),
            info.context.user,
        )  # type: ignore


@strawberry.input
class ManageMembershipInput:
    id: strawberry.ID = strawberry.field(
        description="ID of the node to modify permissions on. This must implement "
        "`Joinable`."
    )
    set_member: Optional[strawberry.ID] = strawberry.field(
        description="ID of a user to add as a non-owning member. If they are already "
        "an owner, they will be demoted."
    )
    set_owner: Optional[strawberry.ID] = strawberry.field(
        description="ID of a user to add as an owner."
    )
    remove_membership: Optional[strawberry.ID] = strawberry.field(
        description="ID of a user whose membership will be removed."
    )
