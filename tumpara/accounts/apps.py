import django.apps


class AccountsConfig(django.apps.AppConfig):
    name = "tumpara.accounts"

    def ready(self) -> None:
        from . import api  # noqa: F401
