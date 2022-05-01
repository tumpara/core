import django.apps
from django.utils.translation import gettext_lazy as _


class AccountsConfig(django.apps.AppConfig):
    name = "tumpara.accounts"
    verbose_name = _("user accounts")

    def ready(self) -> None:
        from . import api  # noqa: F401
