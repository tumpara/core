import django.apps
from django.utils.translation import gettext_lazy as _


class GalleryConfig(django.apps.AppConfig):
    name = "tumpara.gallery"
    verbose_name = _("gallery")

    def ready(self) -> None:
        from tumpara import api

        from . import api as gallery_api  # noqa: F401

        @api.schema.before_finalizing
        def load_gallery_asset_list_query() -> None:
            from .api import gallery_asset_list  # noqa: F401
