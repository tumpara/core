from __future__ import annotations

import abc
import base64
import binascii
from typing import Any, cast

import graphql
import strawberry
import strawberry.types.types
from django.db import models


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
    type_name: str, info: graphql.GraphQLResolveInfo
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
    def id(root: Any, info: graphql.GraphQLResolveInfo) -> strawberry.ID:
        type_name = info.path.typename
        assert isinstance(
            type_name, str
        ), "could not determine type name for resolving node ID"

        origin, type_definition = get_node_origin(type_name, info)
        key = origin.get_key_for_node(root, info)
        key_tuple = (key,) if isinstance(key, str) else key

        return cast(strawberry.ID, encode_key(type_definition.name, *key_tuple))

    @classmethod
    def get_key_for_node(
        cls, root: Any, info: graphql.GraphQLResolveInfo
    ) -> str | tuple[str, ...]:
        """Extract the key used to generate a unique ID for an instance of this Node.

        For Django objects, the default implementation will return the primary key.
        """
        if isinstance(root, models.Model):
            return str(root.pk)
        else:
            raise NotImplementedError(
                f"Cannot generate a global ID for object of type {type(root)!r}. If "
                f"this is not intentional, extend the Node type and override the "
                f"'get_key' method."
            )

    @classmethod
    @abc.abstractmethod
    def get_node_from_key(cls, info: graphql.GraphQLResolveInfo, *key: str) -> Any:
        """Resolve an instance of this node type from the global ID's key."""
