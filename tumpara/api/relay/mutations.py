from __future__ import annotations

import abc
import dataclasses
import enum
import inspect
import typing
from collections.abc import Mapping
from typing import Any, ClassVar, Generic, Optional, TypeVar, cast

import strawberry.arguments
from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import encoding
from strawberry.field import StrawberryAnnotation, StrawberryField

from ..utils import InfoType, is_type_optional, type_annotation_for_django_field
from .base import DjangoNode, _DjangoNode, resolve_node

_Form = TypeVar("_Form", bound="forms.Form | forms.ModelForm[Any]")
_ModelForm = TypeVar("_ModelForm", bound="forms.ModelForm[Any]")


@strawberry.type(
    description="This error is returned when one or more fields fail to pass form "
    "validation in a mutation."
)
class FormError:
    fields: list[str] = strawberry.field(
        description="Names of the fields that did not pass validation."
    )
    codes: list[Optional[str]] = strawberry.field(
        description="Error codes for the specified fields. This list will have the "
        "same length as `fields`. Note that some error codes are not returned. For "
        "example, both permission and not found errors on the `id` field will always "
        "have a nullish error code."
    )

    def __init__(self, fields: list[str], codes: list[Optional[str]]):
        assert len(fields) == len(codes), (
            "validation errors must contain the same number of field names and error "
            "codes"
        )
        self.fields = fields
        self.codes = codes


@strawberry.type(
    description="This error is returned when a node for a mutation could not be "
    "resolved. This might also be the case if the caller has insufficient permissions."
)
class NodeError:
    requested_id: Optional[strawberry.ID] = strawberry.field(
        description="ID of the node that should have been resolved."
    )


@dataclasses.dataclass
class DjangoFormInput(Generic[_Form], abc.ABC):
    _form: ClassVar[type]

    def __init_subclass__(cls, **kwargs: Any):
        form_class: Optional[type[_Form]] = None

        for base in cls.__orig_bases__:  # type: ignore
            origin = typing.get_origin(base)
            if origin is Generic:
                super().__init_subclass__(**kwargs)
                return
            elif inspect.isclass(origin) and issubclass(origin, DjangoFormInput):
                (form_class,) = typing.get_args(base)

        if not hasattr(cls, "_form"):
            cls._form = cast(type[_Form], form_class)
        assert cls._form is not None and issubclass(
            cls._form, (forms.Form, forms.ModelForm)
        ), (
            f"DjangoFormType classes must be initialized with a Django form (got "
            f"{form_class!r}"
        )

        api_fields_with_default = list[StrawberryField]()

        for field_name, form_field in cls._form.base_fields.items():
            # Skip fields that have already been defined.
            if hasattr(cls, field_name):
                continue

            assert isinstance(form_field, forms.Field)

            try:
                # When there is already an annotation (but no matching field), use that.
                # This might be the case for enums or other complex type that need to
                # be modeled individually and are not generated automatically.
                type_annotation = typing.get_type_hints(cls)[field_name]
            except KeyError:
                type_annotation = cls._get_field_type_annotation(form_field)
                cls.__annotations__[field_name] = type_annotation

            if is_type_optional(type_annotation):
                default_value = None
            elif form_field.initial is not None:
                # For non-optional arguments, we can try and see if the model field has
                # defined a default value. Note that the 'initial' property doesn't
                # necessarily mean the default value that is saved when the form is
                # submitted blank, but ModelForm seems to populate this value with the
                # model field's default and that's enough for our use case.
                if inspect.isclass(type_annotation) and issubclass(
                    type_annotation, enum.Enum
                ):
                    # Resolve the enum.
                    default_value = type_annotation(form_field.initial)
                else:
                    default_value = strawberry.arguments.UNSET
            else:
                default_value = strawberry.arguments.UNSET

            api_field = StrawberryField(
                python_name=field_name,
                type_annotation=StrawberryAnnotation(type_annotation),
                default=default_value,
                description=encoding.force_str(form_field.help_text),
            )

            if default_value is strawberry.arguments.UNSET:
                setattr(cls, field_name, api_field)
            else:
                # Defer adding this field because those with a default argument must
                # come last.
                api_fields_with_default.append(api_field)

        for api_field in api_fields_with_default:
            field_name = api_field.python_name
            setattr(cls, field_name, api_field)
            # Re-add the annotation to the __annotations__ dictionary to make sure that
            # the dataclass decorator sees it after the other existing fields (because
            # we need to make sure that fields with a default value are last).
            type_annotation = cls.__annotations__.pop(field_name)
            cls.__annotations__[field_name] = type_annotation

        super().__init_subclass__(**kwargs)

    def _create_form(
        self, info: InfoType, data: dict[Any, Any], **kwargs: Any
    ) -> _Form | FormError | NodeError:
        processed_data = dict[Any, Any]()
        for key, value in data.items():
            if isinstance(value, enum.Enum):
                # Resolve the enum value, because the Django form probably expects
                # the integer or whatever.
                processed_data[key] = value.value
            else:
                processed_data[key] = value
        return cast(_Form, self._get_form_type()(processed_data, **kwargs))

    def prepare(self, info: InfoType) -> _Form | FormError | NodeError:
        """Create an actual (potentially bound) instance of the form that contains all
        the provided data.

        If the form is valid, this will return the form. Otherwise and appropriate error
        is returned.

        .. note::
            When an error occurs, note that it will be *returned* and not *raised*.
            Further, the error will be an actual GraphQL object type and not a Python
            exception. This is done so that the error can directly be returned to the
            API caller.
        """
        form = self._create_form(info, dataclasses.asdict(self))
        if not isinstance(form, self._get_form_type()):
            return form

        if not form.is_valid():
            fields = list[str]()
            codes = list[Optional[str]]()
            for field_name, error_list in form.errors.items():
                for error in error_list.data:
                    fields.append(field_name)
                    if isinstance(error, ValidationError):
                        codes.append(error.code)
                    else:
                        codes.append(None)
            return FormError(fields=fields, codes=codes)

        return form

    @classmethod
    def _get_field_type_annotation(cls, form_field: forms.Field) -> object:
        return type_annotation_for_django_field(form_field)

    @classmethod
    def _get_form_type(cls) -> type[_Form]:
        assert issubclass(cls._form, (forms.Form, forms.ModelForm))
        return cast(type[_Form], cls._form)


@dataclasses.dataclass
class DjangoModelFormInput(
    Generic[_ModelForm, _DjangoNode], DjangoFormInput[_ModelForm], abc.ABC
):
    _node: ClassVar[type[DjangoNode[Any]]]
    _related_permissions: ClassVar[Mapping[str, str]]

    def __init_subclass__(cls, **kwargs: Any):
        node_class: Optional[type[_DjangoNode]] = None

        for base in cls.__orig_bases__:  # type: ignore
            origin = typing.get_origin(base)
            if origin is Generic:
                super().__init_subclass__(**kwargs)
                return
            elif inspect.isclass(origin) and issubclass(origin, DjangoFormInput):
                (node_class,) = typing.get_args(base)

        if not hasattr(cls, "_form"):
            cls._node = cast(type[_DjangoNode], node_class)
        assert cls._form is not None and issubclass(cls._node, DjangoNode), (
            f"DjangoModelFormType classes must be initialized with a DjangoNode class "
            f"(got {node_class!r}"
        )

        kwargs.setdefault("related_permissions", {})
        related_permissions = kwargs.pop("related_permissions")
        if not isinstance(related_permissions, Mapping):
            raise TypeError(
                "related object permission names must be a string dictionary"
            )
        cls._related_permissions = related_permissions

        super().__init_subclass__(**kwargs)
        if any(
            typing.get_origin(base) is Generic
            for base in cls.__orig_bases__  # type: ignore
        ):
            return

        assert cls._form is not None and issubclass(cls._form, forms.ModelForm), (
            f"model form input type classes must be initialized with a Django model "
            f"form (got {cls._form!r})"
        )

    @classmethod
    def _get_model_type(cls) -> type[models.Model]:
        return cls._get_form_type()._meta.model  # type: ignore

    @classmethod
    def _get_node_type(cls) -> type[_DjangoNode]:
        return cls._node  # type: ignore

    def _create_form(
        self, info: InfoType, data: dict[Any, Any], **kwargs: Any
    ) -> _ModelForm | FormError | NodeError:
        from tumpara.accounts.utils import build_permission_name

        for field_name in data.keys():
            if field_name in self._related_permissions:
                # Resolve the ID of the related object into a node, and then get the
                # actual object from there.
                assert isinstance(data[field_name], (str, strawberry.ID))
                node = resolve_node(
                    info, data[field_name], self._related_permissions[field_name]
                )
                if not isinstance(node, DjangoNode):
                    return NodeError(requested_id=data[field_name])
                data[field_name] = node._obj

        if not info.context.user.has_perm(
            build_permission_name(self._get_model_type(), "add")
        ):
            return NodeError(requested_id=None)

        return super()._create_form(info, data, **kwargs)

    @classmethod
    def get_resolving_permission(cls) -> Optional[str]:
        return None

    def resolve(self, info: InfoType) -> _DjangoNode | FormError | NodeError:
        form = self.prepare(info)
        if not isinstance(form, self._get_form_type()):
            return form

        obj = form.save(commit=False)
        assert isinstance(obj, self._get_model_type())
        assert isinstance(obj, self._get_node_type()._get_model_type())

        if (
            resolving_permission := self.get_resolving_permission()
        ) is not None and not info.context.user.has_perm(resolving_permission, obj):
            return NodeError(requested_id=None)

        obj.save()
        form.save_m2m()
        return self._get_node_type()(obj)


@dataclasses.dataclass
class CreateFormInput(Generic[_ModelForm], DjangoModelFormInput[_ModelForm], abc.ABC):
    def get_resolving_permission(cls) -> str:
        from tumpara.accounts.utils import build_permission_name

        return build_permission_name(cls._get_model_type(), "add")


@dataclasses.dataclass
class UpdateFormInput(Generic[_ModelForm], DjangoModelFormInput[_ModelForm], abc.ABC):
    id: strawberry.ID = strawberry.field(description="ID of the object to update.")

    @classmethod
    def _get_field_type_annotation(cls, form_field: forms.Field) -> object:
        type_annotation = super()._get_field_type_annotation(form_field)
        # Make the field optional.
        if not is_type_optional(type_annotation):
            type_annotation = Optional[type_annotation]
        return type_annotation

    def _create_form(
        self, info: InfoType, data: dict[Any, Any], **kwargs: Any
    ) -> _ModelForm | FormError | NodeError:
        from tumpara.accounts.utils import build_permission_name

        node = resolve_node(info, self.id)
        if node is None:
            return NodeError(requested_id=self.id)
        assert isinstance(node, DjangoNode)
        assert isinstance(node._obj, self._get_model_type())
        if not info.context.user.has_perm(
            build_permission_name(node._obj, "change"), node._obj
        ):
            return NodeError(requested_id=self.id)

        return super()._create_form(
            info,
            {
                key: getattr(node._obj, key) if value is None else value
                for key, value in data.items()
            },
            instance=node._obj,
            **kwargs,
        )
