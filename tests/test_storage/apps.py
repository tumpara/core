from django.apps import AppConfig

from tumpara.libraries import signals as libraries_signals
from tumpara.libraries import storage


class TestStorageConfig(AppConfig):
    name = "tests.test_storage"

    def ready(self) -> None:
        from .models import GenericHandler
        from .storage import TestingStorage

        libraries_signals.new_file.connect(
            GenericHandler.handle_new_file, sender="test_storage"
        )
        libraries_signals.files_changed.connect(
            GenericHandler.handle_files_changed,
            sender=GenericHandler,
        )

        storage.register("testing", TestingStorage)
