import os
import shutil

from django.conf import settings


def clean_storages() -> None:
    """Cleanup all storages filled by Tumpara."""
    shutil.rmtree(settings.THUMBNAIL_STORAGE.base_location)
    os.mkdir(settings.THUMBNAIL_STORAGE.base_location)
