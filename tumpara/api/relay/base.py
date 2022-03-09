from __future__ import annotations

import abc
import base64
import binascii
from typing import Any, Optional, cast

import strawberry
import strawberry.types.types
from django.db import models

from ..utils import InfoType


def decode_key(value: str) -> tuple[str, ...]:
    """Decode a set of strings from the serialized representation."""
    try:
        joined_string = base64.b64decode(value.encode()).decode()
    except binascii.Error:
        raise ValueError("failed to decode key: " + value)
    return tuple(joined_string.split(":"))


def encode_key(*values: str | object) -> str:
    """Encode a set of strings into a serialized representation.

    This is useful for encoding IDs, cursors or other keys that can be handed to
    clients where they are treated as a black box. Note that values are not encrypted
    and could be decoded by clients.

    The current implementation will join values together with semicolons and encode the
    result using Base64.
    """
    joined_string = ":".join(map(str, values))
    return base64.b64encode(joined_string.encode()).decode()


def get_node_origin(
    type_name: str, info: InfoType
) -> tuple[type[Node], strawberry.types.types.TypeDefinition]:
    """Get the actual :class:`Node` subclass from a type name.

    :return: Tuple containing the subclass and the type definition.
    """
    schema: Any = info.schema
    assert isinstance(schema, strawberry.Schema), (
        f"got invalid schema type {type(schema)!r} (expected a schema from "
        f"Strawberry) "
    )

    type_definition = schema.get_type_by_name(type_name)
    if not isinstance(type_definition, strawberry.types.types.TypeDefinition):
        # This error is passed to clients.
        raise TypeError(
            f"Could not resolve type name {type_name!r} into an actual type."
        )

    origin = type_definition.origin
    assert issubclass(
        origin, Node
    ), f"expected a Node subclass for resolving IDs, got {origin}"

    return origin, type_definition


@strawberry.interface
class Node(abc.ABC):
    """An object that can be globally referenced with an ID."""

    @strawberry.field(description="The ID of the object.")
    def id(root: Any, info: InfoType) -> strawberry.ID:
        type_name = info.path.typename
        assert isinstance(
            type_name, str
        ), "could not determine type name for resolving node ID"

        origin, type_definition = get_node_origin(type_name, info)
        key = origin.get_key_for_node(root, info)
        key_tuple = (key,) if isinstance(key, str) else key

        return cast(strawberry.ID, encode_key(type_definition.name, *key_tuple))

    @classmethod
    def get_key_for_node(cls, node: Any, info: InfoType) -> str | tuple[str, ...]:
        """Extract the key used to generate a unique ID for an instance of this Node.

        For Django objects, the default implementation will return the primary key.
        """
        if isinstance(node, models.Model):
            return str(node.pk)
        else:
            raise NotImplementedError(
                f"Cannot generate a global ID for object of type {type(node)!r}. If "
                f"this is not intentional, extend the Node type and override the "
                f"'get_key_for_node' method."
            )

    @classmethod
    @abc.abstractmethod
    def get_node_from_key(cls, info: InfoType, *key: str) -> Any:
        """Resolve an instance of this node type from the global ID's key."""


@strawberry.type
class Query:
    @strawberry.field(description="Resolve a node by its ID.")
    def node(root: Any, info: InfoType, id: strawberry.ID) -> Optional[Node]:
        type_name, *key = decode_key(str(id))
        origin, _ = get_node_origin(type_name, info)
        node = origin.get_node_from_key(info, *key)

        if node is None:
            return None

        if hasattr(origin, "is_type_of"):
            assert origin.is_type_of(node, info), (  # type: ignore
                "get_node_from_key() must return an object that is compatible with "
                "is_type_of() "
            )

        return cast(Node, node)
