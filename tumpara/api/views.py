from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import strawberry
import strawberry.django.context
import strawberry.django.views
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.http.response import HttpResponseBase
from django.utils.decorators import method_decorator
from django.views.decorators import csrf

if TYPE_CHECKING:
    from tumpara.accounts import models as accounts_models

    from . import models as api_models
    from .schema import SchemaManager


@dataclasses.dataclass
class ApiContext(strawberry.django.context.StrawberryDjangoContext):
    token: Optional[api_models.Token]
    user: Union[accounts_models.AnonymousUser, accounts_models.User]


class ApiView(strawberry.django.views.GraphQLView):
    schema_manager: Optional[SchemaManager] = None

    def __init__(
        self,
        schema_manager: SchemaManager,
        graphiql: bool = True,
        subscriptions_enabled: bool = False,
        **kwargs: Any,
    ):
        super().__init__(
            schema=None,  # type: ignore
            graphiql=graphiql,
            subscriptions_enabled=subscriptions_enabled,
            **kwargs,
        )
        self.schema_manager = schema_manager

    @property
    def schema(self) -> strawberry.Schema:
        return self.schema_manager.get()

    @schema.setter
    def schema(self, schema: Any) -> None:
        # This assertion will hopefully fail if some upstream implementation fails.
        assert schema is None

    @method_decorator(csrf.csrf_exempt)
    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        if (
            not self.should_render_graphiql(request)
            and (request.method or "get").lower() != "post"
        ):
            # For this implementation, we limit ourselves to POST for the actual GraphQL
            # requests, because Strawberry doesn't actually implement GET yet.
            return HttpResponseNotAllowed(
                ["POST"],
                "Tumpara's GraphQL implementation only supports POST requests.",
            )

        response = super().dispatch(request, *args, **kwargs)  # type: ignore
        return cast(HttpResponseBase, response)

    def get_context(self, request: HttpRequest, response: HttpResponse) -> Any:
        from tumpara.accounts import models as accounts_models

        from . import models as api_models

        token_header = request.headers.get("X-Token")
        token: Optional[api_models.Token] = None
        if token_header:
            try:
                token = (
                    api_models.Token.objects.filter_valid()
                    .prefetch_related("user")
                    .get(key=token_header)
                )
            except api_models.Token.DoesNotExist:
                pass

        user: Union[accounts_models.AnonymousUser, accounts_models.User]
        if token is not None:
            user = token.user
        else:
            user = accounts_models.AnonymousUser()

        return ApiContext(request=request, response=response, token=token, user=user)
