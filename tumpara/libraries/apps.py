import django.apps
from django.utils.translation import gettext_lazy as _


class LibrariesConfig(django.apps.AppConfig):
    name = "tumpara.libraries"
    verbose_name = _("libraries and storage")

    def ready(self) -> None:
        from tumpara import api

        from . import api as libraries_api  # noqa: F401
        from . import storage
        from .storage.file import FileSystemLibraryStorage

        storage.register("file", FileSystemLibraryStorage)

        @api.schema.before_finalizing
        def load_assets_query() -> None:
            from .api import assets_query  # noqa: F401
