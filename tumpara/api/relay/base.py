from __future__ import annotations

import abc
import base64
import binascii
import dataclasses
import inspect
import typing
from collections.abc import Collection
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Optional, TypeVar, cast

import django.db.models.fields.related
import strawberry
import strawberry.types.types
from django.db import models
from django.utils import encoding
from strawberry.field import StrawberryAnnotation, StrawberryField

from ..utils import (
    InfoType,
    NonGenericTypeDefinition,
    extract_optional_type,
    type_annotation_for_django_field,
)

if TYPE_CHECKING:
    from _typeshed import Self

_Node = TypeVar("_Node", bound="Node", covariant=True)
_Model = TypeVar("_Model", bound="models.Model", covariant=True)
_DjangoNode = TypeVar("_DjangoNode", bound="DjangoNode[Any]", covariant=True)


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
    def id(self, info: InfoType) -> strawberry.ID:
        type_name = info.path.typename
        assert isinstance(
            type_name, str
        ), "could not determine type name for resolving node ID"

        origin, type_definition = get_node_origin(type_name, info)
        key = self.get_key(info)
        key_tuple = (key,) if isinstance(key, str) else key

        return cast(strawberry.ID, encode_key(type_definition.name, *key_tuple))

    def get_key(self, info: InfoType) -> str | tuple[str, ...]:
        """Extract the key used to generate a unique ID for an instance of this Node.

        The key may be a string or a tuple of strings.
        """
        raise NotImplementedError(
            f"Cannot generate a global ID for object of type {type(self)!r}. If "
            f"this is not intentional, extend the Node type and override the "
            f"'get_key_for_node' method."
        )

    @classmethod
    @abc.abstractmethod
    def from_key(
        cls: type[Self], info: InfoType, permission: Optional[str] = None, *key: str
    ) -> Optional[Self]:
        """Resolve an instance of this node type from the global ID's key.

        :param info: GraphQL info data.
        :param permission: Optional permission the current user should have. If the
            permission is not fulfilled, this method will return `None`.
        :param key: Parts of the ID.
        """


@strawberry.type
class DjangoNode(Generic[_Model], Node, abc.ABC):
    _model: ClassVar[type[models.Model]]
    _related_field_nodes: ClassVar[dict[str, type[DjangoNode[Any]]]]
    # The following field is not exposed through GraphQL. It is used by DjangoNodeField
    # to resolve attribute values.
    _obj: strawberry.Private[_Model]

    def __init_subclass__(cls, **kwargs: Any):
        model: Optional[type[_Model]] = None

        for base in cls.__orig_bases__:  # type: ignore
            origin = typing.get_origin(base)
            if origin is Generic:
                super().__init_subclass__(**kwargs)
                return
            elif origin is DjangoNode:
                try:
                    (model,) = typing.get_args(base)
                except ValueError:
                    continue
                if not inspect.isclass(model) or not issubclass(model, models.Model):
                    model = None
                    continue
                break

        assert model is not None and issubclass(
            model, models.Model
        ), f"DjangoNode classes must be initialized with a Django model (got {model!r})"
        cls._model = model
        cls._related_field_nodes = dict[str, type[DjangoNode[Any]]]()

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
                type_annotation = typing.get_type_hints(cls)[field_name]
            except KeyError:
                type_annotation = type_annotation_for_django_field(model_field)

            if isinstance(model_field, models.ForeignKey):
                # Validate that the user-provided types for related fields match up.
                try:
                    inner_type = extract_optional_type(type_annotation)
                except TypeError:
                    inner_type = type_annotation
                assert inspect.isclass(inner_type)
                assert issubclass(inner_type, DjangoNode)
                # For some reason, mypy thinks inner_type is <nothing> here.
                assert model_field.remote_field.model is inner_type._get_model_type()  # type: ignore
                cls._related_field_nodes[field_name] = inner_type
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
            # Django fields don't need to be in the constructor because they have a
            # resolver that handles that.
            api_field.init = False
            setattr(cls, field_name, api_field)
            cls.__annotations__[field_name] = type_annotation

        super().__init_subclass__(**kwargs)

    def __getattribute__(self, name: str) -> Any:
        # Proxy attribute access to the model object. This is required so that the
        # fields work.
        if name.startswith("_") or name not in self._get_field_names():
            return super().__getattribute__(name)

        if name in self._related_field_nodes:
            obj = getattr(self._obj, name)
            node_type = self._related_field_nodes[name]
            assert issubclass(node_type, DjangoNode)
            if obj is None:
                return None
            else:
                assert isinstance(obj, node_type._get_model_type())
                return node_type(obj)
        else:
            return getattr(self._obj, name)

    def get_key(self, info: InfoType) -> str:
        """Extract the key used to generate a unique ID for an instance of this Node.

        For Django objects, the default implementation will return the primary key.
        """
        return str(self._obj.pk)

    @classmethod
    def from_key(
        cls: type[_DjangoNode],
        info: InfoType,
        permission: Optional[str] = None,
        *key: str,
    ) -> Optional[_DjangoNode]:
        from tumpara.accounts.utils import build_permission_name

        model = cls._get_model_type()
        resolved_permission = permission or build_permission_name(model, "view")

        assert len(key) == 1, "invalid key format"

        try:
            obj = cls.get_queryset(info, resolved_permission).get(pk=key[0])
        except model.DoesNotExist:
            return None
        except NotImplementedError:
            # We don't have a queryset that respects permissions, so we need to check
            # ourselves.
            try:
                obj = model._default_manager.get(pk=key[0])
            except model.DoesNotExist:
                return None
            if not info.context.user.has_perm(resolved_permission, obj):
                return None

        return cls(obj)

    @classmethod
    def _get_field_names(cls) -> Collection[str]:
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
    def _get_model_type(cls) -> type[_Model]:
        assert issubclass(cls._model, models.Model)
        return cast(type[_Model], cls._model)

    @classmethod
    def get_queryset(cls, info: InfoType, permission: str) -> models.QuerySet[_Model]:
        """Return the default queryset for fetching model objects.

        This queryset must respect the provided permission string. That means that the
        resulting queryset should only contain objects where the current user has the
        given permission. By default, this will be something like
        ``app.view_something``, but may be different for writable use cases.
        """
        raise NotImplementedError


def resolve_node(
    info: InfoType, node_id: str, permission: Optional[str] = None
) -> Optional[Node]:
    """Resolve a single node instance by an ID.

    :param info: GraphQL info data.
    :param node_id: The node ID to resolve.
    :param permission: Optional permission the current user should have. The node will
        not be resolved if this permission is not fulfilled. Django nodes default to the
        viewing permission here.
    """
    type_name, *key = decode_key(node_id)
    origin, _ = get_node_origin(type_name, info)
    return origin.from_key(info, permission, *key)
