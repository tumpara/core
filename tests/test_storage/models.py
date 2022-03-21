from __future__ import annotations

from typing import Optional

from django.contrib.contenttypes import models as contenttypes_models
from django.db import models

from tumpara.libraries import models as libraries_models


class GenericHandler(models.Model):
    """Generic file handler that is used for testing.

    This is intended to be a content object for library records with any file type.
    """

    initialized = models.BooleanField(default=False)
    content = models.BinaryField()

    @staticmethod
    def handle_new_file(
        sender: str, path: str, library: libraries_models.Library
    ) -> Optional[GenericHandler]:
        if sender != "test_storage":
            return None
        return GenericHandler()

    @staticmethod
    def handle_files_changed(
        sender: contenttypes_models.ContentType, record: libraries_models.Record
    ) -> None:
        first_file = record.files.first()
        assert first_file is not None
        handler = record.content_object
        assert isinstance(handler, GenericHandler)
        with first_file.open("rb") as file_io:
            handler.content = file_io.read()
