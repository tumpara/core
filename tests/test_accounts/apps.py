from django.apps import AppConfig

from tumpara.libraries import signals as libraries_signals
from tumpara.libraries import storage


class TestLibrariesConfig(AppConfig):
    name = "tests.test_accounts"

    def ready(self) -> None:
        from . import api  # noqa: F401
