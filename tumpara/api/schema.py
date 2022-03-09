from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import django.http
import django.urls
import django.utils
import strawberry.django.views
import strawberry.tools
import strawberry.types.execution

from tumpara.accounts import api as accounts_api

from . import base as base_api
from . import relay
from .utils import ApiContext
from .views import ApiView

if TYPE_CHECKING:
    from tumpara.accounts import models as accounts_models

    from . import models as api_models

__all__ = ["schema", "urlpatterns"]

Query = strawberry.tools.merge_types(
    "Query", (base_api.Query, relay.base.Query, accounts_api.Query)
)
Mutation = strawberry.tools.merge_types("Mutation", (base_api.Mutation,))
schema = strawberry.Schema(query=Query, mutation=Mutation)


def execute_sync(
    query: str,
    authentication: Optional[accounts_models.User | api_models.Token] = None,
    /,
    **variables: Any,
) -> strawberry.types.execution.ExecutionResult:
    """Shorthand for directly executing a query against the GraphQL schema.

    :param query: The query or mutation to be run.
    :param authentication: Optional authentication information that will be encoded into
        the request. This may either be an existing API token for a user or a user
        directly.
    :param variables: Any other keyword arguments will be processed as query variables.
    """
    from tumpara.accounts import models as accounts_models

    from . import models as api_models

    context: ApiContext
    if isinstance(authentication, api_models.Token):
        context = ApiContext(
            request=django.http.HttpRequest(),
            response=strawberry.django.views.TemporalHttpResponse(),
            user=authentication.user,
            token=authentication,
        )
    else:
        context = ApiContext(
            request=django.http.HttpRequest(),
            response=strawberry.django.views.TemporalHttpResponse(),
            user=authentication or accounts_models.AnonymousUser(),
            token=None,
        )

    return schema.execute_sync(query, variable_values=variables, context_value=context)


urlpatterns = [
    django.urls.path(
        "api/graphql",
        # Note: once we enable subscriptions here, the graphiql.html template needs
        # to be updated from here:
        # https://github.com/strawberry-graphql/strawberry/blob/68901da94c67a7bbd4901d0f0e524da5158442aa/strawberry/static/graphiql.html
        # The subscription-specific stuff was removed because the template isn't
        # currently rendered with any context if it is loaded from the app folder.
        ApiView.as_view(schema=schema),
    ),
]
