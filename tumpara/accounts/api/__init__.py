from typing import Optional

import strawberry

from tumpara import api

from .. import models as accounts_models
from .memberships import JoinableNode, ManageMembershipInput
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
            assert isinstance(info.context.user, accounts_models.User)
            return UserNode(info.context.user)
        else:
            return None


@api.schema.mutation
class Mutation:
    def manage_memberships(self, input: ManageMembershipInput) -> None:
        pass
