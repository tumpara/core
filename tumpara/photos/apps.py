import django.apps
from django.utils.translation import gettext_lazy as _

from tumpara.libraries.signals import new_file, scan_finished


class PhotosConfig(django.apps.AppConfig):
    name = "tumpara.photos"
    verbose_name = _("photos")

    def ready(self) -> None:
        from . import api  # noqa: F401
        from .models import Photo

        new_file.connect(Photo.handle_new_file, sender="gallery")
        scan_finished.connect(Photo.handle_scan_finished)
