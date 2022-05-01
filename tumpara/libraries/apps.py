import django.apps
from django.utils.translation import gettext_lazy as _


class LibrariesConfig(django.apps.AppConfig):
    name = "tumpara.libraries"
    verbose_name = _("libraries and storage")

    def ready(self) -> None:
        from . import api  # noqa: F401
        from . import storage
        from .storage.file import FileSystemLibraryStorage

        storage.register("file", FileSystemLibraryStorage)
