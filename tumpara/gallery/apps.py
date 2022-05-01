import django.apps
from django.utils.translation import gettext_lazy as _


class GalleryConfig(django.apps.AppConfig):
    name = "tumpara.gallery"
    verbose_name = _("gallery")

    def ready(self) -> None:
        from . import api  # noqa: F401
