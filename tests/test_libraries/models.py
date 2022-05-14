from __future__ import annotations

from typing import Any, Optional

from django.db import models, transaction

from tumpara.libraries.models import (
    AssetManager,
    AssetModel,
    AssetQuerySet,
    File,
    Library,
)


class GenericHandlerManagerBase(AssetManager["GenericHandler"]):
    def get_queryset(self) -> models.QuerySet[GenericHandler]:
        files_queryset = File.objects.filter(
            asset__pk=models.OuterRef("pk"),
            availability__isnull=False,
        )
        return super().get_queryset().filter(models.Exists(files_queryset))


GenericHandlerManager = GenericHandlerManagerBase.from_queryset(AssetQuerySet)


class GenericHandler(AssetModel):
    """Generic file handler that is used for testing.

    This is intended to be a content object for library assets with any file type.
    """

    initialized = models.BooleanField(default=False)
    content = models.BinaryField()

    objects = GenericHandlerManager()
    all_objects = models.Manager()

    @staticmethod
    def handle_new_file(
        context: str, path: str, library: Library, **kwargs: Any
    ) -> Optional[GenericHandler]:
        if context != "test_storage":
            return None
        with library.storage.open(path, "rb") as file_io:
            content = file_io.read()
        handler, _ = GenericHandler.all_objects.get_or_create(
            library=library, content=content
        )
        return handler

    @staticmethod
    @transaction.atomic
    def handle_files_changed(
        sender: type[GenericHandler],
        asset: GenericHandler,
        **kwargs: Any,
    ) -> None:
        if sender is not GenericHandler or not isinstance(asset, GenericHandler):
            pass

        for file in asset.files.filter(availability__isnull=False).order_by("-pk"):
            try:
                with file.open("rb") as file_io:
                    file_content = file_io.read()
            except IOError:
                # This case might occur if we still have an old database entry of a file
                # that the scanner hasn't yet gotten to.
                file.availability = None
                file.save()
                continue

            if file_content != asset.content:
                # Move this file out to another handler, because the content doesn't
                # match anymore.
                new_asset, created = GenericHandler.all_objects.get_or_create(
                    library=asset.library, content=file_content
                )
                file.asset = new_asset
                file.save()

        asset.initialized = True
        asset.save()

    @staticmethod
    def assert_unique_contents() -> None:
        """Make sure that all handlers have unique content."""
        for library in GenericHandler.objects.values_list("library").distinct():
            contents = list(
                GenericHandler.objects.filter(library=library).values_list("content")
            )
            assert sorted(set(contents)) == sorted(contents)
