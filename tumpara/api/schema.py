from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional

import django.http
import django.urls
import django.utils
import strawberry.django.views
import strawberry.schema.schema
import strawberry.tools
import strawberry.types.execution

from .utils import ApiContext

if TYPE_CHECKING:
    from tumpara.accounts.models import User

    from .models import Token


class SchemaManager:
    def __init__(self) -> None:
        self.config = strawberry.schema.schema.StrawberryConfig()
        self._schema: Optional[strawberry.Schema] = None
        self._queries = list[type]()
        self._mutations = list[type]()
        self._before_schema_finalizing = list[Callable[..., Any]]()

    def _ensure_schema_is_not_built(self) -> None:
        assert self._schema is None, (
            "Trying to register a new type with the already-built schema. This is "
            "disallowed because it is probably a bug. It means that the actual GraphQL "
            "schema has already been accessed before all types were registered."
        )

    @staticmethod
    def prep_type(given_type: type, *, is_input: bool = False) -> type:
        if dataclasses.is_dataclass(given_type):
            return given_type
        else:
            return strawberry.type(given_type, is_input=is_input)

    def query(self, query_type: type) -> type:
        """Register a query type that will be merged into the final schema."""
        self._ensure_schema_is_not_built()
        query_type = self.prep_type(query_type)
        self._queries.append(query_type)
        return query_type

    def mutation(self, mutation_type: type) -> type:
        """Register a mutation type that will be merged into the final schema."""
        self._ensure_schema_is_not_built()
        mutation_type = self.prep_type(mutation_type)
        self._mutations.append(mutation_type)
        return mutation_type

    def before_finalizing(self, callback: Callable[..., Any]) -> Callable[..., Any]:
        """Register a callback that will be called just before the final schema is
        built.

        This can be useful to defer specific types that depend on some sort of other
        registration pattern.
        """
        self._before_schema_finalizing.append(callback)

    def get(self) -> strawberry.Schema:
        if self._schema is None:
            for callback in self._before_schema_finalizing:
                callback()

            merged_query = strawberry.tools.merge_types("Query", tuple(self._queries))
            merged_mutation = strawberry.tools.merge_types(
                "Mutation", tuple(self._mutations)
            )
            self._schema = strawberry.Schema(
                config=self.config,
                query=merged_query,
                mutation=merged_mutation,
            )
        return self._schema


schema = SchemaManager()


def execute_sync(
    query: str,
    authentication: Optional[User | Token] = None,
    /,
    operation_name: Optional[str] = None,
    **variables: Any,
) -> strawberry.types.execution.ExecutionResult:
    """Shorthand for directly executing a query against the GraphQL schema.

    :param query: The query or mutation to be run.
    :param authentication: Optional authentication information that will be encoded into
        the request. This may either be an existing API token for a user or a user
        directly.
    :param variables: Any other keyword arguments will be processed as query variables.
    """
    from tumpara.accounts.models import AnonymousUser

    from .models import Token

    context: ApiContext
    if isinstance(authentication, Token):
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
            user=authentication or AnonymousUser(),
            token=None,
        )

    return schema.get().execute_sync(
        query,
        variable_values=variables,
        context_value=context,
        operation_name=operation_name,
    )
