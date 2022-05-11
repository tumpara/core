from django.apps import AppConfig


class TestLibrariesConfig(AppConfig):
    name = "tests.test_accounts"

    def ready(self) -> None:
        from . import api  # noqa: F401
