from __future__ import annotations

import dataclasses
import inspect
import typing
from collections.abc import Callable, Iterator, Sequence
from typing import Any, ClassVar, Generic, Optional, TypeVar, Union, cast

import strawberry.annotation
import strawberry.arguments
from django.db import models
from strawberry.field import StrawberryField
from strawberry.type import StrawberryOptional

from tumpara.accounts.utils import build_permission_name
from tumpara.api import filtering

from ..utils import InfoType
from .base import DjangoNode, _DjangoNode, _Model, _Node, decode_key, encode_key

_DjangoConnection = TypeVar("_DjangoConnection", bound="DjangoConnection[Any, Any]")
_Connection = TypeVar("_Connection", bound="Connection[Any]")


@strawberry.type(
    description="""Pagination context for a connection.

See the [Relay specification](https://relay.dev/graphql/connections.htm) for
details.
"""
)
class PageInfo:
    has_next_page: bool = strawberry.field(
        description="Whether a next page is available for paginating forwards (using "
        "`first`). This respects the `before` argument, but ignores any potential "
        "value for `last`. When not paginating forwards, this will be `false`."
    )
    has_previous_page: bool = strawberry.field(
        description="Whether a next page is available for paginating backwards (using "
        "`last`). This respects the `after` argument, but ignores any potential "
        "value for `first`. When not paginating backwards, this will be `false`."
    )
    start_cursor: Optional[str] = strawberry.field(
        description="The cursor to continue with when paginating backwards."
    )
    end_cursor: Optional[str] = strawberry.field(
        description="The cursor to continue with when paginating forwards."
    )


@dataclasses.dataclass
class Edge(Generic[_Node]):
    """An edge in a connection. This points to a single item in the dataset."""

    node: _Node
    cursor: str = strawberry.field(
        description="A cursor used for pagination in the corresponding connection."
    )

    def __init_subclass__(cls, **kwargs: Any):
        # Delay the field initialization code, see this method in the Connection class
        # for details.
        cls.node = strawberry.field(  # type: ignore
            description="The node connected to the edge.",
        )

        super().__init_subclass__(**kwargs)


@strawberry.type
class Connection(Generic[_Node]):
    """A connection to a list of items."""

    # We use Sequence here because the argument needs to be covariant (so that
    # subclasses can override it).
    edges: Sequence[Optional[Edge[_Node]]]
    nodes: list[Optional[_Node]]
    page_info: PageInfo = strawberry.field(
        description="Pagination information for fetching more objects in the "
        "connection's dataset."
    )
    total_count: Optional[int] = strawberry.field(
        description="Total number of results in the dataset, ignoring pagnation."
    )

    def __init_subclass__(cls, **kwargs: Any):
        if any(
            typing.get_origin(base) is Generic
            for base in cls.__orig_bases__  # type: ignore
        ):
            super().__init_subclass__(**kwargs)
            return

        if "name" not in kwargs or "pluralized_name" not in kwargs:
            raise TypeError("name and pluralized_name parameters must be provided")
        name = kwargs.pop("name")
        assert isinstance(name, str)
        pluralized_name = kwargs.pop("pluralized_name")
        assert isinstance(pluralized_name, str)

        # There are a few reasons why these field initialization stuff is delayed and
        # done here rather than directly giving edges and nodes a field in the class.
        #
        # First, Strawberry still has a few problems with generics, needing us to
        # manually resolve them in the subclass. That's why all the connection
        # subclasses redefine the actual properties.
        #
        # Further, Mypy also does not currently resolve subclasses of generic
        # dataclasses correctly:
        #   https://github.com/python/mypy/issues/10039#issuecomment-774304871
        #   https://github.com/python/mypy/issues/12063
        #
        # The workaround is to manually redefine all affected properties in the subclass
        # and then add the fields (with their description) again here.
        cls.edges = strawberry.field(  # type: ignore
            description=f"A list of {name} edges in the connection."
        )
        cls.nodes = strawberry.field(  # type: ignore
            description=f"A list of {pluralized_name} in the connection. This is the "
            "same as querying `{ edges { node } }`, so when no edge data (like the "
            "cursor) is needed, this field can be used instead.",
        )

        super().__init_subclass__(**kwargs)

    @classmethod
    def empty(cls: type[_Connection], total_count: int = 0) -> _Connection:
        return cls(
            page_info=PageInfo(
                has_next_page=False,
                has_previous_page=False,
                start_cursor=None,
                end_cursor=None,
            ),
            total_count=total_count,
            edges=[],
            nodes=[],
        )

    @classmethod
    def _get_edge_type(cls) -> type[Edge[_Node]]:
        try:
            field_annotation = typing.get_type_hints(cls)["edges"]
            assert typing.get_origin(field_annotation) is list
            optional_annotation = typing.get_args(field_annotation)[0]
            assert typing.get_origin(optional_annotation) in (Optional, Union)
            inner_annotation = next(
                arg for arg in typing.get_args(optional_annotation) if arg is not None
            )
            assert issubclass(inner_annotation, Edge)
            return cast(type[Edge[_Node]], inner_annotation)
        except Exception as error:
            raise TypeError(
                "Could not extract edge type from annotations - make sure the 'edges' "
                "field is annotated like this: list[Optional[SomeEdge]]. Also note "
                "that the node type of the edge and the connection should match."
            ) from error

    @classmethod
    def from_sequence(
        cls: type[_Connection],
        sequence: Sequence[_Node],
        *,
        after: Optional[str] = None,
        before: Optional[str] = None,
        first: Optional[int] = None,
        last: Optional[int] = None,
    ) -> _Connection:
        after_index: Optional[int] = None
        if after is not None:
            try:
                after_context, after_index_string = decode_key(after)
                after_index = int(after_index_string)
                assert after_context == "Connection"
            except (ValueError, AssertionError) as error:
                raise ValueError("invalid after cursor: " + after) from error

        before_index: Optional[int] = None
        if before is not None:
            try:
                before_context, before_index_string = decode_key(before)
                before_index = int(before_index_string)
                assert before_context == "Connection"
            except (ValueError, AssertionError) as error:
                raise ValueError("invalid before cursor: " + before) from error

        if first is not None and first < 0:
            raise ValueError("'first' option must be non-negative")
        if last is not None and last < 0:
            raise ValueError("'last' option must be non-negative")

        sequence_length = len(sequence)

        # Default to an empty result.
        if first == 0 or last == 0 or (first is None and last is None):
            return cls.empty(sequence_length)

        # The following algorithm more or less follows the one provided in the Relay
        # specification:
        # https://relay.dev/graphql/connections.htm#sec-Pagination-algorithm

        # Step 1: build the initial slice by looking at the 'before' and 'after'
        # arguments. Note that for Python slices, the start value is inclusive and the
        # stop value is exclusive. Both may be None, but always having a start value is
        # helpful below, so we set it to zero when no after cursor is provided.
        slice_start = after_index + 1 if after_index is not None else 0
        slice_stop = before_index if before_index is not None else sequence_length
        # Slices can index from the back using negative numbers. We don't want that
        # here, so that needs to be clamped:
        slice_start = max(0, min(slice_start, sequence_length))
        slice_stop = max(0, min(slice_stop, sequence_length))

        if slice_stop is not None and slice_start >= slice_stop:
            return cls.empty(sequence_length)

        # See the specification again for this algorithm:
        # https://relay.dev/graphql/connections.htm#sec-undefined.PageInfo.Fields
        # This is densed down a bit (see the descriptions of has_previous_page and
        # has_next_page in our model for details).
        has_previous_page = False
        if last is not None:
            has_previous_page = slice_stop - slice_start > last
        has_next_page = False
        if first is not None:
            has_next_page = slice_stop - slice_start > first

        # Step 2: limit the result to at most the number of entries specified in the
        # 'first' argument, counting from the front.
        if first is not None:
            # The end of the slice is exclusive. As an example, for after=0 and first=2
            # we want the first two elements after index zero:
            #   [0, 1, 2, 3, 4][1:0+3] = [1, 2]
            slice_stop = min(slice_stop, slice_start + first)

        # Step 3: limit the result according to the 'last' argument, counting from the
        # back.
        if last is not None:
            # Another example: before=5 and last=1 yields:
            #   [0, 1, 2, 3, 4][5-1:5] = [4]
            slice_start = max(slice_start, slice_stop - last)

        edge_type = cls._get_edge_type()
        edges = [
            edge_type(node=item, cursor=encode_key("Connection", index + slice_start))
            for index, item in enumerate(sequence[slice_start:slice_stop])
        ]
        # MyPy doesn't get that cls is actually a dataclass:
        return cls(
            page_info=PageInfo(
                has_next_page=has_next_page,
                has_previous_page=has_previous_page,
                start_cursor=edges[0].cursor if len(edges) > 0 else None,
                end_cursor=edges[-1].cursor if len(edges) > 0 else None,
            ),
            total_count=sequence_length,
            edges=edges,
            nodes=[edge.node if edge is not None else None for edge in edges],
        )


class DjangoConnection(Generic[_DjangoNode, _Model], Connection[_DjangoNode]):
    """A connection superclass for connections with Django models."""

    _node: ClassVar[type]
    _model: ClassVar[type]

    def __init_subclass__(cls, **kwargs: Any):
        node: Optional[type[_DjangoNode]] = None
        model: Optional[type[_Model]] = None

        for base in cls.__orig_bases__:  # type: ignore
            origin = typing.get_origin(base)
            if origin is Generic:
                super().__init_subclass__(**kwargs)
                return
            elif origin is DjangoConnection:
                (node, model) = typing.get_args(base)

        assert node is not None and issubclass(
            node, DjangoNode
        ), f"DjangoConnection classes must be created with a DjangoNode (got {node!r})"
        assert model is not None and issubclass(model, models.Model), (
            f"DjangoConnection classes must be created with a Django model "
            f"(got {model!r})"
        )
        assert (
            node._get_model_type() is model
        ), "a DjangoConnection must point to the same model as the accompanying node"
        cls._node = node
        cls._model = model

        super().__init_subclass__(**kwargs)

    @classmethod
    def _get_node_type(cls) -> type[_DjangoNode]:
        assert issubclass(cls._node, DjangoNode)
        return cast(type[_DjangoNode], cls._node)

    @classmethod
    def _get_model_type(cls) -> type[_Model]:
        assert issubclass(cls._model, models.Model)
        return cast(type[_Model], cls._model)

    @classmethod
    def get_queryset(cls, info: InfoType, permission: str) -> models.QuerySet[_Model]:
        """Return the queryset that :class:`DjangoConnectionField` uses to resolve
        model objects.

        By default, this uses :meth:`DjangoNode.get_queryset` on the Django node. As
        described there, make sure that this method handles permissions correctly.
        """
        return cls._get_node_type().get_queryset(info, permission)

    @classmethod
    def create_node(cls, obj: _Model) -> _DjangoNode:
        """Create a node from a model instance.

        The default implementation instantiates the node type the connection was
        initialized with. You may want to override this method if the node type is an
        interface.
        """
        return cls._get_node_type()(obj)

    @classmethod
    def from_queryset(
        cls: type[_DjangoConnection],
        queryset: models.QuerySet[_Model],
        info: InfoType,
        *,
        after: Optional[str] = None,
        before: Optional[str] = None,
        first: Optional[int] = None,
        last: Optional[int] = None,
    ) -> _DjangoConnection:
        # We don't check the generic view permission on the model here anymore because
        # we assume that the connection's (which calls the node's) get_queryset method
        # already filters accordingly.

        # Since Connection.from_sequence expects a sequence of nodes (the API type) and
        # we only have a queryset (which yields model instances), we need to transform
        # that accordingly.
        class NodeSequence:
            def __getitem__(self, item: int | slice) -> NodeSequence:
                nonlocal queryset
                assert isinstance(item, slice)
                queryset = queryset[item]
                return self

            def __iter__(self) -> Iterator[_Node]:
                for obj in queryset:
                    assert isinstance(obj, cls._get_model_type())
                    yield cls.create_node(obj)

            def __len__(self) -> int:
                return queryset.count()

        return cls.from_sequence(
            cast(Sequence[DjangoNode], NodeSequence()),
            after=after,
            before=before,
            first=first,
            last=last,
        )


class ConnectionField(StrawberryField):
    """Connection field that automatically adds the ``after``, ``before``, ``first``
    and ``last`` arguments.

    When providing a resolver, you can pass these remaining keyword arguments directly
    to :meth:`Connection.from_sequence`, without needing to define them.
    """

    @property
    def arguments(self) -> list[strawberry.arguments.StrawberryArgument]:
        arguments_map = {
            argument.python_name: argument for argument in super().arguments
        }

        def add_argument(
            name: str, type_annotation: object | str, description: str
        ) -> None:
            arguments_map.setdefault(
                name,
                strawberry.arguments.StrawberryArgument(
                    python_name=name,
                    graphql_name=None,
                    type_annotation=strawberry.annotation.StrawberryAnnotation(
                        type_annotation
                    ),
                    description=description,
                ),
            )

        add_argument(
            "after",
            Optional[str],
            "Return only items in the dataset that come after this cursor.",
        )
        add_argument(
            "before",
            Optional[str],
            "Return only items in the dataset that come before this cursor.",
        )
        add_argument(
            "first",
            Optional[int],
            "Return at most this many items, counting from the start.",
        )
        add_argument(
            "last",
            Optional[int],
            "Return at most this many items, counting from the end.",
        )

        # When defining a resolver for the actual connection, we often use a pattern
        # like this:
        #
        #   def resolve_the_connection(other_argument: int, **kwargs: Any):
        #       ...
        #       return TheConnection.from_sequence(iterable, **kwargs)
        #
        # To get around Strawberry automatically adding a field for the keyword
        # arguments, we manually delete it here.
        if "kwargs" in arguments_map:
            del arguments_map["kwargs"]

        return list(arguments_map.values())


class DjangoConnectionField(ConnectionField):
    """Connection field for Django connections.

    The default resolver will use :meth:`DjangoConnection.get_queryset` instead of
    Strawberry's default :func:`getattr` implementation. Provide another resolver by
    using the field as a decorator. Note that resolvers for Django connection fields
    should not return the connection, but rather a :class:`models.QuerySet`.

    The optional ``filter`` argument can be specified to support filtering results.
    This should be an input type that has a ``build_query`` method that matches that
    of other filter types.
    """

    def __init__(
        self,
        connection_type: Optional[type[DjangoConnection[Any, Any]]] = None,
        description: Optional[str] = None,
        filter_type: Optional[type[filtering.GenericFilter]] = None,
        **kwargs: Any,
    ):
        if connection_type is not None:
            kwargs.setdefault(
                "type_annotation",
                Optional[connection_type],
            )

        super().__init__(description=description, **kwargs)
        self.filter_type = filter_type

    def __call__(
        self, resolver: Callable[Any, models.QuerySet[Any]]  # type: ignore
    ) -> DjangoConnectionField:
        super().__call__(resolver)
        assert self.base_resolver is not None
        assert self.type_annotation is not None, (
            "a type annotation (the connection type) must be provided when using a "
            "custom resolver in Django connection fields"
        )
        # Propagate our type annotation (if available) to the resolver. That way the
        # resolver can return (type-checked) querysets and the API will still have the
        # connection type.
        self.base_resolver.annotations["return"] = self.type_annotation
        return self

    @property
    def arguments(self) -> list[strawberry.arguments.StrawberryArgument]:
        arguments = super().arguments
        if self.filter_type is None:
            return arguments

        for argument in arguments:
            assert (
                argument.python_name != "filter"
            ), "DjangoConnectionField resolvers must not have a 'filter' argument"

        return [
            *arguments,
            strawberry.arguments.StrawberryArgument(
                python_name="filter",
                graphql_name=None,
                type_annotation=strawberry.annotation.StrawberryAnnotation(
                    Optional[self.filter_type]
                ),
                description="Filter to narrow down results.",
            ),
        ]

    def get_result(
        self, source: Any, info: InfoType, args: list[Any], kwargs: dict[str, Any]
    ) -> Any:
        connection_type = self.type
        # If our type is optional, we want the actual content type.
        if isinstance(connection_type, StrawberryOptional):
            connection_type = connection_type.of_type
        assert inspect.isclass(connection_type) and issubclass(
            connection_type, DjangoConnection
        ), (
            f"Django connection fields must have resolve to a DjangoConnection type, "
            f"got {type(connection_type)}"
        )

        if self.base_resolver:
            queryset = self.base_resolver(*args, **kwargs)
        else:
            try:
                view_permission = build_permission_name(
                    connection_type._get_model_type(), "view"
                )
                queryset = connection_type.get_queryset(info, view_permission)
            except NotImplementedError as error:
                raise AssertionError(
                    "cannot resolve a Django connection that does not define "
                    "get_queryset()"
                ) from error
        assert isinstance(queryset, models.QuerySet)
        assert issubclass(queryset.model, connection_type._get_model_type()), (
            f"queryset model type {queryset.model} must match the connection model "
            f"type {connection_type._get_model_type()}"
        )

        if (
            self.filter_type is not None
            and (filter := kwargs.pop("filter", None)) is not None
        ):
            # Since we are filtering objects directly in the queryset (and not some
            # subfield), the field name is an empty string here:
            query_result = filter.build_query("")
            if isinstance(query_result, models.Q):
                query, aliases = query_result, {}
            else:
                query, aliases = query_result
            queryset = queryset.alias(**aliases).filter(query)

        kwargs.setdefault("info", info)
        # It should be safe to ignore 'args' here, because that only contains the
        # self / root / parent value for the original resolver.
        return connection_type.from_queryset(queryset, **kwargs)
