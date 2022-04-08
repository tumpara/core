from __future__ import annotations

import abc
import base64
import binascii
import datetime
import decimal
import typing
from collections.abc import Collection
from typing import Any, ClassVar, Generic, Optional, TypeVar, cast

import strawberry
import strawberry.types.types
from django.db import models
from django.utils import encoding
from strawberry.field import StrawberryAnnotation, StrawberryField

from ..utils import InfoType

_Node = TypeVar("_Node", bound="Node")
_DjangoNode = TypeVar("_DjangoNode", bound="DjangoNode")
_Model = TypeVar("_Model", bound="models.Model")


def decode_key(value: str) -> tuple[str, ...]:
    """Decode a set of strings from the serialized representation."""
    try:
        joined_string = base64.b64decode(value.encode()).decode()
    except binascii.Error as error:
        raise ValueError("failed to decode key: " + value) from error
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
        """Extract the key used to generate a unique ID for an instance of this Node."""
        raise NotImplementedError(
            f"Cannot generate a global ID for object of type {type(node)!r}. If "
            f"this is not intentional, extend the Node type and override the "
            f"'get_key_for_node' method."
        )

    @classmethod
    @abc.abstractmethod
    def get_node_from_key(cls, info: InfoType, *key: str) -> Any:
        """Resolve an instance of this node type from the global ID's key."""


class NonGenericTypeDefinition(strawberry.types.types.TypeDefinition):
    is_generic = False


class DjangoNodeField(StrawberryField):
    @property
    def arguments(self) -> list[strawberry.arguments.StrawberryArgument]:
        return []

    def get_result(self, source: Any, *args: Any, **kwargs: Any) -> Any:
        assert isinstance(source, DjangoNode)
        assert isinstance(source._obj, models.Model)
        return super().get_result(source._obj, *args, **kwargs)


@strawberry.interface
class DjangoNode(Generic[_Model], Node, abc.ABC):
    _model: ClassVar[type[_Model]]

    def __init__(self, obj: _Model):
        if not isinstance(obj, self._model):
            raise
        self._obj = obj

    def __init_subclass__(cls, **kwargs):
        model: Optional[type[_Model]] = None

        for base in cls.__orig_bases__:  # type: ignore
            origin = typing.get_origin(base)
            if origin is Generic:
                super().__init_subclass__(**kwargs)
                return
            elif origin is DjangoNode:
                (model,) = typing.get_args(base)

        assert model is not None and issubclass(
            model, models.Model
        ), f"DjangoNode classes must be initialized with a Django model (got {model!r})"
        cls._model = model

        # Patch the is_generic field because we know that our type isn't actually
        # generic anymore and Strawberry doesn't currently support this situation:
        # https://github.com/strawberry-graphql/strawberry/issues/1195
        cls._type_definition.__class__ = NonGenericTypeDefinition  # type: ignore

        if "fields" not in kwargs or not isinstance(kwargs["fields"], Collection):
            raise TypeError("fields argument is mandatory for DjangoNode")

        for field_name in kwargs.pop("fields"):
            if not isinstance(field_name, str):
                raise TypeError("field names must be given as strings")

            model_field = model._meta.get_field(field_name)
            assert isinstance(model_field, models.Field)

            if model_field.choices:
                raise ValueError("converting fields with choices is not supported yet")

            type_annotation: object
            if isinstance(model_field, models.BooleanField):
                type_annotation = bool
            elif isinstance(model_field, (models.CharField, models.TextField)):
                type_annotation = str
            elif isinstance(model_field, models.IntegerField):
                type_annotation = int
            elif isinstance(model_field, models.FloatField):
                type_annotation = float
            elif isinstance(model_field, models.DecimalField):
                type_annotation = decimal.Decimal
            elif isinstance(model_field, models.DateField):
                type_annotation = datetime.date
            elif isinstance(model_field, models.DateTimeField):
                type_annotation = datetime.datetime
            elif isinstance(model_field, models.TimeField):
                type_annotation = datetime.time
            else:
                raise TypeError(f"unknown field type: {type(model_field)}")

            if model_field.null:
                type_annotation = Optional[type_annotation]

            api_field = DjangoNodeField(
                python_name=field_name,
                type_annotation=StrawberryAnnotation(type_annotation),
                description=encoding.force_str(model_field.help_text),
            )
            setattr(cls, field_name, api_field)
            cls.__annotations__[field_name] = type_annotation

        super().__init_subclass__(**kwargs)

    @classmethod
    def get_node_from_key(cls, info: InfoType, *key: str) -> Any:
        assert len(key) == 1, "invalid key format"
        return cls._model._default_manager.get(pk=key[0])

    @classmethod
    def get_key_for_node(cls, node: Any, info: InfoType) -> str | tuple[str, ...]:
        """Extract the key used to generate a unique ID for an instance of this Node.

        For Django objects, the default implementation will return the primary key.
        """
        if isinstance(node, DjangoNode):
            return str(node._obj.pk)
        else:
            return super().get_key_for_node(node, info)


def resolve_node(info: InfoType, id: strawberry.ID) -> Optional[Node]:
    from tumpara.accounts.utils import build_permission_name

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

    if isinstance(node, models.Model) and not info.context.user.has_perm(
        build_permission_name(node, "view"), node
    ):
        return None

    return cast(Node, node)


@strawberry.type
class Query:
    node: Optional[Node] = strawberry.field(
        resolver=resolve_node, description="Resolve a node by its ID."
    )
