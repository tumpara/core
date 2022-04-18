from __future__ import annotations

import abc
import base64
import binascii
import dataclasses
import typing
from collections.abc import Collection
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Optional, TypeVar, cast

import django.db.models.fields.related
import strawberry
import strawberry.types.types
from django.db import models
from django.utils import encoding
from django.utils.functional import cached_property
from strawberry.field import StrawberryAnnotation, StrawberryField

from ..utils import (
    InfoType,
    NonGenericTypeDefinition,
    extract_optional_type,
    type_annotation_for_django_field,
)

if TYPE_CHECKING:
    from _typeshed import Self

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
    def get_node_from_key(cls: type[Self], info: InfoType, *key: str) -> Optional[Self]:
        """Resolve an instance of this node type from the global ID's key."""


@strawberry.interface
class DjangoNode(Generic[_Model], Node, abc.ABC):
    _model: ClassVar[type[_Model]]
    _related_field_nodes: ClassVar[dict[str, type[DjangoNode[Any]]]]
    # The following two fields are not be exposed via GraphQL. Instead, they are only
    # here so that resolvers have access.
    pk: strawberry.Private[str]
    _obj: strawberry.Private[Optional[_Model]]

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
        cls._related_field_nodes = {}

        # Patch the is_generic field (see the class' docstring for details).
        cls._type_definition.__class__ = NonGenericTypeDefinition  # type: ignore

        if "fields" not in kwargs or not isinstance(kwargs["fields"], Collection):
            raise TypeError("fields argument is mandatory for DjangoNode")

        for field_name in kwargs.pop("fields"):
            if not isinstance(field_name, str):
                raise TypeError("field names must be given as strings")

            model_field = model._meta.get_field(field_name)
            assert isinstance(model_field, models.Field)

            try:
                # Re-use existing annotations. This might be the case for non-scalar
                # field types like relationships.
                type_annotation = cls.__annotations__[field_name]
            except KeyError:
                type_annotation = type_annotation_for_django_field(model_field)

            if isinstance(model_field, models.ForeignKey):
                # Validate that the user-provided types for related fields match up.
                # This is used by from_obj() to recursively resolve related objects.
                try:
                    inner_type = extract_optional_type(type_annotation)
                except TypeError:
                    inner_type = type_annotation
                assert issubclass(inner_type, DjangoNode)
                assert model_field.remote_field.model is inner_type._model
                cls._related_field_nodes[field_name] = type_annotation
            elif isinstance(model_field, django.db.models.fields.related.RelatedField):
                raise TypeError(
                    "Related fields are not supported for automatic schema mapping. "
                    "Please provide a custom field with resolver instead."
                )

            api_field = StrawberryField(
                python_name=field_name,
                type_annotation=StrawberryAnnotation(type_annotation),
                description=encoding.force_str(model_field.help_text),
            )
            setattr(cls, field_name, api_field)
            cls.__annotations__[field_name] = type_annotation

        super().__init_subclass__(**kwargs)

    @cached_property
    def obj(self) -> _Model:
        """The model object this node refers to.

        If possible, it is preferred to use the primary key attribute :attr:`pk` of the
        node instead. The object may not always be available and might cause another
        database query.
        """
        if self._obj is None:
            self._obj = self._model._default_manager.get(pk=self.pk)
        return self._obj

    @classmethod
    def field_names(cls) -> Collection[str]:
        """Return the names of all fields required to initialize a node."""
        result = [
            # The primary key field would be filtered out in the following loop, so we
            # include it here.
            "pk",
        ]
        for field in dataclasses.fields(cls):
            if not isinstance(field, StrawberryField):
                continue
            if field.base_resolver is not None:
                # This field has its own resolver.
                continue
            result.append(field.name)
        return result

    @classmethod
    def from_obj(cls: type[Self], obj: _Model) -> Self:
        """Create a node instance from a Django model object.

        If possible, consider using :meth:`from_queryset` instead.
        """
        kwargs = dict[str, Any]()
        for field_name in cls.field_names():
            value = getattr(obj, field_name)
            if field_name in cls._related_field_nodes:
                value = cls._related_field_nodes[field_name].from_obj(value)
            kwargs[field_name] = value
        return cls(_obj=obj, **kwargs)

    @classmethod
    def from_queryset(cls: type[Self], queryset: models.QuerySet[_Model]) -> Self:
        """Create a node instance from a single-entry queryset.

        The provided queryset should:

        - Contain exactly one item (:meth:`~models.QuerySet.count` should return 1).
        - Already be filtered according to the appropriate permissions. No further
          checks will be performed.
        """
        assert queryset.model is cls._model
        values = queryset.values(cls.field_names()).get()
        return cls(_obj=None, **values)

    @classmethod
    def get_queryset(cls, info: InfoType) -> models.QuerySet[_Model]:
        """Return the default queryset for fetching model objects.

        This queryset must respect view permissions for the current user. That means
        anything where the user does not have the ``app.view_something`` permission
        must not be included in this queryset. If this method is not implemented, the
        default manager will be used and the permission check will be performed on each
        object individually.
        """
        raise NotImplementedError

    @classmethod
    def get_node_from_key(cls: type[Self], info: InfoType, *key: str) -> Optional[Self]:
        from tumpara.accounts.utils import build_permission_name

        assert len(key) == 1, "invalid key format"
        if not info.context.user.has_perm(build_permission_name(cls._model, "view")):
            return None

        try:
            obj = cls.get_queryset(info).get(pk=key[0])
        except NotImplementedError:
            # We don't have a queryset that respects permissions, so we need to check
            # ourselves.
            obj = cls._model._default_manager.get(pk=key[0])
            if not info.context.user.has_perm(
                build_permission_name(cls._model, "view"), obj
            ):
                return None

        return cls.from_obj(obj)

    @classmethod
    def get_key_for_node(cls, node: Any, info: InfoType) -> str:
        """Extract the key used to generate a unique ID for an instance of this Node.

        For Django objects, the default implementation will return the primary key.
        """
        assert isinstance(node, cls)
        return str(node.pk)


def resolve_node(info: InfoType, node_id: str) -> Optional[Node]:
    type_name, *key = decode_key(node_id)
    origin, _ = get_node_origin(type_name, info)
    return origin.get_node_from_key(info, *key)
