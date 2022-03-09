import django.db.models
from django.contrib.contenttypes.models import ContentType

__all__ = ["build_permission_name"]


def build_permission_name(
    model: django.db.models.Model | type[django.db.models.Model], action: str
) -> str:
    content_type = ContentType.objects.get_for_model(model, for_concrete_model=True)
    app_label = content_type.app_label
    model_name = model._meta.model_name
    assert isinstance(model_name, str), "unknown model name for building permission"
    return f"{app_label}.{action}_{model_name}"
