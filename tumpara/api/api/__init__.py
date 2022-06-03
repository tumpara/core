from typing import Annotated, Optional, cast

import strawberry
from django.contrib import auth
from django.utils import timezone

from tumpara import api
from tumpara.accounts.api import UserNode
from tumpara.accounts.models import User

from ..models import Token
from ..utils import with_argument_annotation


@strawberry.type(name="Token", description=Token.__doc__ or "")
class TokenNode(api.DjangoNode, fields=["key", "user", "expiry_timestamp", "name"]):
    obj: strawberry.Private[Token]
    user: UserNode

    def __init__(self, _obj: Token):
        self.obj = _obj


@strawberry.type(
    description="Information on password authentication.\n\n"
    "To login using a username and password, use the `createToken` mutation. The "
    "parameter `credentials` should be set to a 2-element list containing the username "
    "and password, in that order."
)
class PasswordAuthentication:
    # This field is required because we can't build an empty object type. Further, this
    # object will only actually be instantiated if password authentication is actually
    # supported, so we always return True.
    @strawberry.field
    def available(self) -> bool:
        return True


@strawberry.type(
    description="Information about an OIDC authentication method.\n\n"
    "Note that none are implemented yet and this type is just a placeholder."
    # TODO Use '#oidc.theprovidername' as the username when creating a token
)
class OIDCAuthentication:
    url: str
    display_name: str


AuthenticationMethod = strawberry.union(
    "AuthenticationMethod", types=(PasswordAuthentication, OIDCAuthentication)
)


@strawberry.type(
    description="Error that is returned from creating a new API token when invalid "
    "credentials are given. This might be the case when:\n"
    "- No user with the given username exists\n"
    "- The password was wrong\n"
    "- The corresponding user has been disabled"
)
class InvalidCredentialsError:
    scope: str = strawberry.field(
        description="For password-based authentication, this will be the username."
        # If the TOTP code was wrong, this will be `#totp`.
    )


@strawberry.type(
    description="Error that is returned from creating a new API token when the form of "
    "the provided credentials can't be mapped to a supported authentication method."
)
class UnknownAuthenticationMethodError:
    method: str = strawberry.field(
        description="The authentication method suggested by the client (or at least a "
        "guess thereof)."
    )


CreateTokenResult = strawberry.union(
    "CreateTokenResult",
    types=(TokenNode, InvalidCredentialsError, UnknownAuthenticationMethodError),
)


@api.schema.query
class Query:
    @strawberry.field(
        description="List of available authentication methods. These can be used with "
        "the `createToken` mutation."
    )
    def authentication_methods(
        self,
    ) -> list[Optional[AuthenticationMethod]]:
        return [PasswordAuthentication()]

    @strawberry.field(description="Resolve a node by its ID.")
    def node(
        self,
        info: api.InfoType,
        node_id: Annotated[
            strawberry.ID,
            strawberry.argument(name="id", description="The global ID to resolve."),
        ],
    ) -> Optional[api.Node]:
        return api.resolve_node(info, str(node_id))


@api.schema.mutation
class Mutation:
    @strawberry.mutation(
        description="Login as a user and create a token for API usage."
    )
    @with_argument_annotation(
        name=strawberry.argument(
            description="Name of the token. Most of the time, this will be the "
            "name of the client application.",
        )
    )
    def create_token(
        self,
        info: api.InfoType,
        credentials: Annotated[
            list[str],
            strawberry.argument(
                description="Credentials to log in with. This must be a list with "
                "length at least one. The first entry here denotes the authentication "
                "method to use, which can be retrieved with the "
                "`authenticationMethods` query. Other values in this list depend on "
                "authentication method.\n\n"
                "When logging in with a username and password, pass them as a 2-tuple "
                "in that order."
            ),
        ],
        name: Optional[str] = api.UNSET,
    ) -> Optional[CreateTokenResult]:
        if len(credentials) == 0:
            return UnknownAuthenticationMethodError(method="")

        user: User

        # Username and password authentication: this uses the normal Django backend for
        # checking a user's password. Here, we assume credentials is given in the form
        # [username, password].
        if not credentials[0].startswith("#"):
            if len(credentials) < 2:
                return InvalidCredentialsError(scope=credentials[0])
            authenticated_user = auth.authenticate(
                info.context.request, username=credentials[0], password=credentials[1]
            )
            if authenticated_user is None or not authenticated_user.is_active:
                return InvalidCredentialsError(scope=credentials[0])
            # Once TOTP is supported, credentials should have a third entry with the
            # token. Otherwise some error like MissingTOTPCodeError should be returned.
            user = cast(User, authenticated_user)

        else:
            return UnknownAuthenticationMethodError(method=credentials[0])

        # Create a token for the user. By default, it will be valid for a week, although
        # that setting should be changeable later on.
        token = user.api_tokens.create(
            expiry_timestamp=timezone.now() + timezone.timedelta(days=7),
            name=name or "",
        )
        return TokenNode(token)
