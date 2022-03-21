from django.apps import AppConfig

from tumpara.libraries import signals as libraries_signals


class TestStorageConfig(AppConfig):
    name = "tests.test_storage"

    def ready(self) -> None:
        from django.contrib.contenttypes.models import ContentType

        from .models import GenericHandler

        libraries_signals.new_file.connect(
            GenericHandler.handle_new_file, sender="test_storage"
        )
        libraries_signals.files_changed.connect(
            GenericHandler.handle_files_changed,
            sender=ContentType.objects.get_for_model(GenericHandler),
        )
