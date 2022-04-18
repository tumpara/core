from __future__ import annotations

from typing import Any, Optional

from django.contrib.contenttypes import fields as contenttypes_fields
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction

from tumpara.libraries import models as libraries_models


class GenericHandlerManager(models.Manager["GenericHandler"]):
    def get_queryset(self) -> models.QuerySet[GenericHandler]:
        files_queryset = libraries_models.File.objects.filter(
            record__object_pk=models.OuterRef("pk"),
            record__content_type=ContentType.objects.get_for_model(GenericHandler),
            availability__isnull=False,
        )
        return super().get_queryset().filter(models.Exists(files_queryset))


class GenericHandler(models.Model):
    """Generic file handler that is used for testing.

    This is intended to be a content object for library records with any file type.
    """

    initialized = models.BooleanField(default=False)
    content = models.BinaryField()
    records = contenttypes_fields.GenericRelation(
        libraries_models.Record, "object_pk", "content_type"
    )

    objects = GenericHandlerManager()
    all_objects = models.Manager()

    @staticmethod
    def handle_new_file(
        context: str, path: str, library: libraries_models.Library, **kwargs: Any
    ) -> Optional[GenericHandler]:
        if context != "test_storage":
            return None
        with library.storage.open(path, "rb") as file_io:
            content = file_io.read()
        handler, _ = GenericHandler.all_objects.get_or_create(
            records__library=library, content=content
        )
        return handler

    @staticmethod
    @transaction.atomic
    def handle_files_changed(
        sender: type[models.Model],
        record: libraries_models.Record,
        **kwargs: Any,
    ) -> None:
        if sender is not GenericHandler:
            pass

        handler = record.content_object
        assert isinstance(handler, GenericHandler)

        for file in record.files.filter(availability__isnull=False).order_by("-pk"):
            try:
                with file.open("rb") as file_io:
                    file_content = file_io.read()
            except IOError:
                # This case might occur if we still have an old database entry of a file
                # that the scanner hasn't yet gotten to.
                file.availability = None
                file.save()
                continue

            if file_content != handler.content:
                # Move this file out to another handler, because the content doesn't
                # match anymore.
                new_handler, created = GenericHandler.all_objects.get_or_create(
                    records__library=record.library, content=file_content
                )
                if created:
                    new_record = libraries_models.Record.objects.create(
                        library=record.library, content_object=new_handler
                    )
                else:
                    new_record = new_handler.records.first()
                file.record = new_record
                file.save()
                new_handler.initialized = True
                new_handler.save()

        handler.initialized = True
        handler.save()

    @staticmethod
    def assert_unique_contents() -> None:
        """Make sure that all handlers have unique content."""
        for library in GenericHandler.objects.values_list(
            "records__library"
        ).distinct():
            contents = list(
                GenericHandler.objects.filter(records__library=library).values_list(
                    "content"
                )
            )
            assert sorted(set(contents)) == sorted(contents)
