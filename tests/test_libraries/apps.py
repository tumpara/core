from django.apps import AppConfig

from tumpara.libraries import storage
from tumpara.libraries.signals import new_file


class TestLibrariesConfig(AppConfig):
    name = "tests.test_libraries"

    def ready(self) -> None:
        from .models import GenericHandler
        from .storage import TestingStorage

        new_file.connect(GenericHandler.handle_new_file, sender="test_storage")

        storage.register("testing", TestingStorage)
