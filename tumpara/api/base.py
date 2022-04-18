import datetime
from typing import Annotated, Any, Optional, cast

import strawberry
from django.contrib import auth
from django.utils import timezone

from tumpara.accounts import api as accounts_api
from tumpara.accounts import models as accounts_models

from . import models as api_models
from .utils import InfoType


@strawberry.type(description=api_models.Token.__doc__ or "")
class Token:
    key: Optional[str] = strawberry.field(
        description=str(api_models.Token._meta.get_field("key").help_text)
    )
    user: accounts_api.UserNode = strawberry.field(
        description=str(api_models.Token._meta.get_field("user").help_text)
    )
    expiry_timestamp: datetime.datetime = strawberry.field(
        description=str(api_models.Token._meta.get_field("expiry_timestamp").help_text)
    )
    name: str = strawberry.field(
        description=str(api_models.Token._meta.get_field("name").help_text)
    )

    @classmethod
    def is_type_of(cls, obj: Any, info: InfoType) -> bool:
        return isinstance(obj, api_models.Token)


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
    types=(Token, InvalidCredentialsError, UnknownAuthenticationMethodError),
)


@strawberry.type
class Query:
    @strawberry.field(
        description="List of available authentication methods. These can be used with "
        "the `createToken` mutation."
    )
    def authentication_methods(
        self,
    ) -> list[Optional[AuthenticationMethod]]:
        return [PasswordAuthentication()]


@strawberry.type
class Mutation:
    @strawberry.mutation(
        description="Login as a user and create a token for API usage."
    )
    def create_token(
        self,
        info: InfoType,
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
        name: Annotated[
            Optional[str],
            strawberry.argument(
                description="Name of the token. Most of the time, this will be the "
                "name of the client application."
            ),
        ],
    ) -> Optional[CreateTokenResult]:
        if len(credentials) == 0:
            return UnknownAuthenticationMethodError(method="")

        user: accounts_models.User

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
            user = cast(accounts_models.User, authenticated_user)

        else:
            return UnknownAuthenticationMethodError(method=credentials[0])

        # Create a token for the user. By default, it will be valid for a week, although
        # that setting should be changeable later on.
        token = user.api_tokens.create(
            expiry_timestamp=timezone.now() + timezone.timedelta(days=7),
            name=name or "",
        )
        return cast(Token, token)
