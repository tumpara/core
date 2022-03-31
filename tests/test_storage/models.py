from __future__ import annotations

from typing import Any, Optional

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
        sender: str, path: str, library: libraries_models.Library, **kwargs: Any
    ) -> Optional[GenericHandler]:
        if sender != "test_storage":
            return None
        return GenericHandler()

    @staticmethod
    def handle_files_changed(
        sender: type[models.Model],
        record: libraries_models.Record,
        **kwargs: Any,
    ) -> None:
        if sender is not GenericHandler:
            pass
        first_file = record.files.first()
        assert isinstance(first_file, libraries_models.File)
        handler = record.content_object
        assert isinstance(handler, GenericHandler)
        with first_file.open("rb") as file_io:
            handler.content = file_io.read()
        handler.initialized = True
        handler.save()
