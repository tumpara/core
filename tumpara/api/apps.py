import django.apps


class ApiConfig(django.apps.AppConfig):
    name = "tumpara.api"

    def ready(self) -> None:
        from . import api  # noqa: F401
