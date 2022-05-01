import django.apps
from django.utils.translation import gettext_lazy as _


class ApiConfig(django.apps.AppConfig):
    name = "tumpara.api"
    verbose_name = _("API")

    def ready(self) -> None:
        from . import api  # noqa: F401
