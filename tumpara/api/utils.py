from __future__ import annotations

import datetime
import decimal
import inspect
import types
import typing
from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated, Any, Optional, TypeVar, Union

import strawberry.types.info
import strawberry.types.types
from django import forms
from django.db import models
from django.utils import encoding

from .views import ApiContext

if TYPE_CHECKING:
    import strawberry.arguments

    from tumpara.accounts import models as accounts_models

_T = TypeVar("_T")

InfoType = strawberry.types.info.Info[ApiContext, None]


class NonGenericTypeDefinition(strawberry.types.types.TypeDefinition):
    """This class is used in a few places to patch the ``is_generic`` field of
    Strawberry types when we know that it definitely isn't generic anymore. Sometimes
    it might be the case that Strawberry doesn't get that the type is actually resolved:
    https://github.com/strawberry-graphql/strawberry/issues/1195
    """

    is_generic = False


def check_authentication(info: InfoType) -> Optional[accounts_models.User]:
    """Check whether a given API call is authenticated.

    If available, the current :class:`accounts_models.User` object will be returned.
    """
    from tumpara.accounts import models as accounts_models

    user = info.context.user
    if user.is_authenticated and user.is_active:
        assert isinstance(user, accounts_models.User)
        return user
    else:
        return None


def type_annotation_for_django_field(
    field: models.Field[Any, Any] | forms.Field
) -> object:
    """Return the correct type annotation for the API field, given a Django field.

    :param field: The Django field for which the equivalent should be returned. This may
        either be a model field or a form field.
    :return: A type annotation for the field. If the field is optional, the result will
        be wrapped in an :func:`Optional`.
    """
    if (isinstance(field, models.Field) and field.choices) or isinstance(
        field, forms.ChoiceField
    ):
        raise ValueError("converting fields with choices is not supported yet")

    type_annotation: object
    if isinstance(field, (models.BooleanField, forms.BooleanField)):
        type_annotation = bool
    elif isinstance(field, (models.CharField, models.TextField, forms.CharField)):
        type_annotation = str
    elif isinstance(field, (models.IntegerField, forms.IntegerField)):
        type_annotation = int
    elif isinstance(field, (models.FloatField, forms.FloatField)):
        type_annotation = float
    elif isinstance(field, (models.DecimalField, forms.DecimalField)):
        type_annotation = decimal.Decimal
    elif isinstance(field, (models.DateField, forms.DateField)):
        type_annotation = datetime.date
    elif isinstance(field, (models.DateTimeField, forms.DateTimeField)):
        type_annotation = datetime.datetime
    elif isinstance(field, (models.TimeField, forms.TimeField)):
        type_annotation = datetime.time
    else:
        raise TypeError(f"unknown field type: {type(field)}")

    if (isinstance(field, models.Field) and field.null) or (
        isinstance(field, forms.Field) and not field.required
    ):
        type_annotation = Optional[type_annotation]

    return type_annotation


def extract_optional_type(type_annotation: object) -> object:
    """Extract the inner type of an optional."""
    # Make sure the type annotation is actually resolved.
    assert not isinstance(type_annotation, str)

    origin = typing.get_origin(type_annotation)
    if origin is Optional:
        return typing.get_args(type_annotation)[0]
    elif origin in (Union, types.UnionType):
        inner_types = list[object]()
        seen_none = False
        for inner_type in typing.get_args(type_annotation):
            if inner_type is type(None):
                seen_none = True
                continue
            inner_types.append(inner_type)

        if not seen_none:
            raise TypeError("provided union type did not contain None")

        assert len(inner_types) > 0
        if len(inner_types) == 1:
            return inner_types[0]
        else:
            result: object = Union[inner_types[0], inner_types[1]]
            for inner_type in inner_types[2:]:
                result = result | inner_type
            return result
    else:
        raise TypeError("provided type was not an optional")


def is_type_optional(type_annotation: object) -> bool:
    """Check whether the given type annotation is an optional."""
    # Make sure the type annotation is actually resolved.
    assert not isinstance(type_annotation, str)

    try:
        extract_optional_type(type_annotation)
        return True
    except TypeError:
        return False


def get_field_description(
    form_or_model: forms.Form
    | type[forms.Form]
    | forms.ModelForm[Any]
    | type[forms.ModelForm[Any]]
    | models.Model
    | type[models.Model],
    field_name: str,
) -> str:
    """Extract the help text from a form field."""
    if (
        inspect.isclass(form_or_model) and issubclass(form_or_model, forms.BaseForm)
    ) or isinstance(form_or_model, forms.BaseForm):
        field = form_or_model.base_fields[field_name]
        return encoding.force_str(field.help_text)
    elif (
        inspect.isclass(form_or_model) and issubclass(form_or_model, models.Model)
    ) or isinstance(form_or_model, models.Model):
        field = form_or_model._meta.get_field(field_name)
        return encoding.force_str(field.help_text)
    else:
        raise TypeError(
            f"expected form or model instance or class, got {form_or_model}"
        )


def with_argument_annotation(
    **annotations: strawberry.arguments.StrawberryArgumentAnnotation,
) -> Callable[[_T], _T]:
    """Add the given annotations to specific arguments on a resolver.

    This should be used as a decorator on resolver methods, before applying
    :func:`strawberry.field` or :func:`strawberry.mutation`. The reason that this exists
    even though ``Annotated[int, strawberry.argument(...)]`` works is because the
    project also uses the django_stubs plugin for MyPy. This specific plugin seems to
    assume that :class:`~typing.Annotated` will always have a non-optional type as the
    first argument and subsequently crashes when using an annotation that is optional.

    To use this decorator, pass the object returned by :func:`strawberry.argument` as
    the keyword arguments for everything that should be decorated. The existing
    annotation will be wrapped in an :class:`~typing.Annotated` with the provided
    augmentation.

    See the implementation of the `create_token` mutation for an example.
    """

    def decorate(resolver: _T) -> _T:
        for name, argument_annotation in annotations.items():
            # We explicitly don't use typing.get_type_hints here because we don't
            # actually need to resolve the end type.
            if name not in resolver.__annotations__:
                raise ValueError(
                    f"could not augment GraphQL field argument because no existing "
                    f"annotation exists: {name}"
                )
            resolver.__annotations__[name] = Annotated[
                resolver.__annotations__[name],
                argument_annotation,
            ]
        return resolver

    return decorate
