from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import strawberry
import strawberry.django.context
import strawberry.django.views
from django.core.files import storage
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.http.response import HttpResponseBase
from django.utils.decorators import method_decorator
from django.views.decorators import csrf
from django.views.static import serve

if TYPE_CHECKING:
    from tumpara.accounts.models import AnonymousUser, User

    from .models import Token
    from .schema import SchemaManager


@dataclasses.dataclass
class ApiContext(strawberry.django.context.StrawberryDjangoContext):
    token: Optional[Token]
    user: Union[AnonymousUser, User]


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

    @property  # type: ignore
    def schema(self) -> strawberry.Schema:
        assert self.schema_manager is not None
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
        from tumpara.accounts.models import AnonymousUser, User

        from .models import Token

        token: Optional[Token] = None
        if token_header := request.headers.get("X-Token"):
            token = Token.objects.check_token(token_header)

        user: Union[AnonymousUser, User]
        if token is not None:
            user = token.user
        else:
            user = AnonymousUser()

        return ApiContext(request=request, response=response, token=token, user=user)


def serve_file(
    request: HttpRequest, file_storage: storage.Storage, file_path: str
) -> HttpResponseBase:
    """Serve a file download.

    :param storage: The storage engine to load the file from.
    :param path: Path inside the storage.
    """
    if isinstance(file_storage, storage.FileSystemStorage):
        # For file system backends, we can serve the file as is, without needing to open
        # it here directly.
        # TODO Use some sort of sendfile-like serving mechanism. See here:
        #  https://github.com/johnsensible/django-sendfile/blob/master/sendfile/backends/nginx.py
        return serve(
            request,
            file_path,
            document_root=str(file_storage.base_location),
        )
    else:
        # TODO Implement this. We probably need to redo the serve() function from above
        #   entirely because we want to support If-Modified-Since headers, content types
        #   and so on.
        raise NotImplementedError(
            "File downloads are not implemented yet for backends other than the "
            "filesystem backend."
        )
