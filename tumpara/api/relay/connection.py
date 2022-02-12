from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any  # noqa: F401
from typing import TYPE_CHECKING, Generic, Optional, TypeVar

import strawberry.annotation
import strawberry.arguments
from strawberry.field import StrawberryField

from .base import Node  # noqa: F401
from .base import decode_key, encode_key

if TYPE_CHECKING:
    from _typeshed import Self

_Node = TypeVar("_Node", bound="Node")


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


def resolve_node_id(root: "Edge[_Node]") -> strawberry.ID:
    return root.node.id


@dataclasses.dataclass
class Edge(Generic[_Node]):
    """An edge in a connection. This points to a single item in the dataset."""

    node: _Node = strawberry.field(description="The node connected to the edge.")
    cursor: str = strawberry.field(
        description="A cursor used for pagination in the corresponding connection."
    )
    node_id: strawberry.ID = strawberry.field(
        resolver=resolve_node_id,
        description="The ID of the node connected to the edge.",
    )


def resolve_connection_nodes(
    root: "Connection[Any]",
) -> list[Optional[Node]]:
    return [edge.node if edge is not None else None for edge in root.edges]


def resolve_connection_node_ids(
    root: "Connection[Any]",
) -> list[Optional[strawberry.ID]]:
    return [edge.node.id if edge is not None else None for edge in root.edges]


@strawberry.type
class Connection(Generic[_Node]):
    """A connection to a list of items."""

    # We use Sequence here because the argument needs to be covariant (so that
    # subclasses can override it). Further, these field() objects are here so we can
    # create Connection() objects (they will be overridden by __init_subclass__).
    edges: Sequence[Optional[Edge[_Node]]]
    nodes: list[Optional[_Node]] = strawberry.field(resolver=resolve_connection_nodes)
    node_ids: list[Optional[strawberry.ID]] = strawberry.field(
        resolver=resolve_connection_node_ids
    )
    page_info: PageInfo = strawberry.field(
        description="Pagination information for fetching more objects in the "
        "connection's dataset."
    )
    total_count: Optional[int] = strawberry.field(
        description="Total number of results in the dataset, ignoring pagnation."
    )

    def __init_subclass__(cls, *args: Any, **kwargs: Any):
        if "name" not in kwargs or "pluralized_name" not in kwargs:
            raise TypeError("name and pluralized_name parameters must be provided")
        name = kwargs.pop("name")
        assert isinstance(name, str)
        pluralized_name = kwargs.pop("pluralized_name")
        assert isinstance(pluralized_name, str)

        cls.edges = strawberry.field(
            description=f"A list of {name} edges in the connection."
        )
        cls.nodes = strawberry.field(
            resolver=resolve_connection_nodes,
            description=f"A list of {pluralized_name} in the connection. This is the "
            "same as querying `{ edges { node } }`, so when no edge data (like the "
            "cursor) is needed, this field can be used instead.",
        )
        cls.node_ids = strawberry.field(
            resolver=resolve_connection_node_ids,
            description=f"A list of the ID of each {name} in the connection. This is "
            "the same as querying `{ edges { node { id } }`.",
        )

        super().__init_subclass__(*args, **kwargs)

    @classmethod
    def from_sequence(
        cls: type[Self],
        sequence: Sequence[_Node],
        size: Optional[int] = None,
        *,
        after: Optional[str] = None,
        before: Optional[str] = None,
        first: Optional[int] = None,
        last: Optional[int] = None,
    ) -> Self:
        after_index: Optional[int] = None
        if after is not None:
            try:
                after_context, after_index_string = decode_key(after)
                after_index = int(after_index_string)
                assert after_context == "Connection"
            except (ValueError, AssertionError):
                raise ValueError("invalid after cursor: " + after)

        before_index: Optional[int] = None
        if before is not None:
            try:
                before_context, before_index_string = decode_key(before)
                before_index = int(before_index_string)
                assert before_context == "Connection"
            except (ValueError, AssertionError):
                raise ValueError("invalid before cursor: " + before)

        if first is not None and first < 0:
            raise ValueError("'first' option must be non-negative")
        if last is not None and last < 0:
            raise ValueError("'last' option must be non-negative")

        sequence_length = size if size is not None else len(sequence)

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
            return cls(  # type: ignore
                page_info=PageInfo(
                    has_next_page=False,
                    has_previous_page=False,
                    start_cursor=None,
                    end_cursor=None,
                ),
                total_count=sequence_length,
                edges=[],
            )

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

        edges = [
            Edge(node=item, cursor=encode_key("Connection", index + slice_start))
            for index, item in enumerate(sequence[slice_start:slice_stop])
        ]
        # MyPy doesn't get that cls is actually a dataclass:
        return cls(  # type: ignore
            page_info=PageInfo(
                has_next_page=has_next_page,
                has_previous_page=has_previous_page,
                start_cursor=edges[0].cursor if len(edges) > 0 else None,
                end_cursor=edges[-1].cursor if len(edges) > 0 else None,
            ),
            total_count=sequence_length,
            edges=edges,
        )


class ConnectionField(StrawberryField):
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
