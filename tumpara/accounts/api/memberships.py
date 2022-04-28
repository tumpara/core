from typing import Generic, Optional, TypeVar

import strawberry
from django.contrib.contenttypes import models as contenttypes_models
from django.db import models

from tumpara import api

from .. import models as accounts_models
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
    def members(self, info: api.InfoType) -> models.QuerySet[accounts_models.User]:
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
