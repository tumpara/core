from __future__ import annotations

import dataclasses
import urllib.parse
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import strawberry
import strawberry.django.context
import strawberry.django.views
from django.core.files import storage as django_storage
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
    request: HttpRequest,
    storage: django_storage.Storage,
    path: str,
    *,
    filename: Optional[str] = None,
) -> HttpResponseBase:
    """Serve a file download.

    :param request: Original HTTP request.
    :param storage: The storage engine to load the file from.
    :param path: Path inside the storage.
    :param filename: String to override the file name in the response.
    """
    if isinstance(storage, django_storage.FileSystemStorage):
        # For file system backends, we can serve the file as is, without needing to open
        # it here directly.
        # TODO Use some sort of sendfile-like serving mechanism. See here:
        #  https://github.com/johnsensible/django-sendfile/blob/master/sendfile/backends/nginx.py
        response = serve(request, path, document_root=str(storage.base_location))
        if filename is not None:
            try:
                filename.encode("ascii")
                encoded_filename = filename.replace("\\", "\\\\").replace('"', r"\"")
                filename_expression = f'filename="{encoded_filename}"'
            except UnicodeEncodeError:
                encoded_filename = urllib.parse.quote(filename)
                filename_expression = f"filename*=utf-8''{encoded_filename}"
            response.headers["Content-Disposition"] = f"inline; {filename_expression}"
        return response
    else:
        # TODO Implement this. We probably need to redo the serve() function from above
        #   entirely because we want to support If-Modified-Since headers, content types
        #   and so on.
        raise NotImplementedError(
            "File downloads are not implemented yet for backends other than the "
            "filesystem backend."
        )
