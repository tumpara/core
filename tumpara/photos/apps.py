import django.apps
from django.utils.translation import gettext_lazy as _

from tumpara.libraries.signals import files_changed, new_file


class PhotosConfig(django.apps.AppConfig):
    name = "tumpara.photos"
    verbose_name = _("photos")

    def ready(self) -> None:
        from .models import Photo

        new_file.connect(Photo.handle_new_file, sender="gallery")
        files_changed.connect(Photo.handle_files_changed, sender=Photo)
