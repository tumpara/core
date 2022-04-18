from __future__ import annotations

import datetime
import decimal
import typing
from typing import TYPE_CHECKING, Optional, Union

import strawberry.types.info
import strawberry.types.types
from django import forms
from django.db import models
from django.utils import encoding

from .views import ApiContext

if TYPE_CHECKING:
    from tumpara.accounts import models as accounts_models

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


def type_annotation_for_django_field(field: models.Field | forms.Field) -> object:
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


def is_type_optional(type_annotation: object) -> bool:
    """Check whether the given type annotation is an optional."""
    origin = typing.get_origin(type_annotation)
    if origin is Optional:
        return True
    elif origin is Union and type(None) in typing.get_args(type_annotation):
        return True
    else:
        return False


def get_field_description(
    form: forms.BaseForm | type[forms.BaseForm], field_name: str
) -> str:
    """Extract the help text from a form field."""
    field = form.base_fields[field_name]
    return encoding.force_str(field.help_text)
