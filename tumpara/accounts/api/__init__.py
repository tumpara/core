from typing import Any, Optional

import strawberry

from tumpara import api

from ..models import Joinable, User
from ..utils import build_permission_name
from .joinables import JoinableNode
from .users import UserConnection, UserFilter, UserNode

__all__ = ["JoinableNode", "UserFilter", "UserNode"]


@api.schema.query
class Query:
    users: Optional[UserConnection] = api.DjangoConnectionField(  # type: ignore
        filter_type=UserFilter,
        description="All users available on this server.",
    )

    @strawberry.field(
        description="The user that is currently accessing the API. For anonymous "
        "sessions, this will be `null`."
    )
    def me(self, info: api.InfoType) -> Optional[UserNode]:
        if api.check_authentication(info):
            assert isinstance(info.context.user, User)
            return UserNode(obj=info.context.user)
        else:
            return None


@strawberry.input
class ManageMembershipInput:
    joinable_id: strawberry.ID = strawberry.field(
        description="ID of the node to modify permissions on. This must implement "
        "`Joinable`."
    )
    user_id: strawberry.ID = strawberry.field(
        description="ID of the user to set permissions for."
    )
    status: Optional[bool] = strawberry.field(
        description="Status the user's membership should have. This may be one "
        "three values:\n\n"
        "- `null` – the user will not be a member. Any existing membership will be "
        "terminated. Note that no precautions will be made around removing the last "
        "remaining user.\n"
        "- `false` – the user will be a regular member.\n"
        "- `true` – the user will be an owner with editing permissions."
    )


@strawberry.type
class ManageMembershipSuccess:
    joinable: JoinableNode
    user: UserNode


ManageMembershipResult = strawberry.union(
    "ManageMembershipResult", types=(ManageMembershipSuccess, api.NodeError)
)


@api.schema.mutation
class Mutation:
    @strawberry.field(description="Update membership status of a user on a joinable.")
    def manage_membership(
        self, info: api.InfoType, input: ManageMembershipInput
    ) -> ManageMembershipResult:
        joinable_node = api.resolve_node(info, input.joinable_id)
        if not isinstance(
            joinable_node, JoinableNode
        ) or not info.context.user.has_perm(
            build_permission_name(joinable_node.obj, "change"), joinable_node.obj
        ):
            return api.NodeError(requested_id=input.joinable_id)
        joinable: Joinable = joinable_node.obj

        user_node = api.resolve_node(info, input.user_id)
        if not isinstance(user_node, UserNode):
            return api.NodeError(requested_id=input.user_id)
        user: User = user_node.obj

        if input.status is None:
            joinable.remove_membership(user)
        else:
            joinable.add_membership(user, owner=input.status)

        return ManageMembershipSuccess(joinable=joinable_node, user=user_node)
