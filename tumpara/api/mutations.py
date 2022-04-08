from typing import Any, Optional, TypeVar

import strawberry
import strawberry.tools
from django import forms

from . import relay
from .utils import InfoType

_Form = TypeVar("_Form", bound="forms.ModelForm")


@strawberry.type(
    description="This error is returned when one or more fields fail to pass form "
    "validation in a mutation."
)
class ValidationError:
    fields: list[str] = strawberry.field(
        description="Names of the fields that did not pass validation."
    )


@strawberry.type(
    description="This error is returned when the user doesn't have the required "
    "permissions to perform a mutation."
)
class PermissionError:
    id: Optional[strawberry.ID] = strawberry.field(
        description="The ID that was requested."
    )


def perpare_model_form(
    form_class: type[_Form],
    info: InfoType,
    *,
    id: Optional[strawberry.ID],
    **kwargs: Any,
) -> _Form | ValidationError | PermissionError:
    from tumpara.accounts.utils import build_permission_name

    if id is not None:
        # resolve_node will take care of view permission checks.
        node = relay.resolve_node(info, id)
        if node is None:
            return ValidationError(fields=["id"])
        if not info.context.user.has_perm(build_permission_name(node, "change")):
            return PermissionError(id=id)
        form = form_class(dict(instance=node, **kwargs))
    else:
        if not info.context.user.has_perm(
            build_permission_name(form_class._meta.model, "add")
        ):
            return PermissionError(id=None)
        form = form_class(kwargs)

    form.clean()
    if not form.is_valid():
        return ValidationError(fields=[field_name for field_name in form.errors.keys()])

    return form
