import django.apps


class LibrariesConfig(django.apps.AppConfig):
    name = "tumpara.libraries"

    def ready(self) -> None:
        from . import api  # noqa: F401
        from . import storage
        from .storage.file import FileSystemLibraryStorage

        storage.register("file", FileSystemLibraryStorage)
