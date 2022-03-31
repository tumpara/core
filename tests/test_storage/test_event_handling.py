from collections.abc import Generator

import freezegun
import pytest
from django.utils import timezone

from tumpara.libraries import models as libraries_models
from tumpara.libraries import scanner

from .models import GenericHandler
from .storage import TestingStorage


@pytest.fixture
def library() -> Generator[libraries_models.Library, None, None]:
    TestingStorage.clear()
    yield libraries_models.Library.objects.create(
        source="testing:///", context="test_storage"
    )
    TestingStorage.clear()


@pytest.mark.django_db
def test_basic_file_scanning(library: libraries_models.Library) -> None:
    """New file events work ."""
    TestingStorage.set("foo", "hello")
    scanner.FileEvent("foo").commit(library)
    # This will also make sure that there is *exactly* one file object.
    file = libraries_models.File.objects.get()
    assert file.library == library
    assert file.path == "foo"
    assert file.availability is not None
    content = file.record.content_object
    assert isinstance(content, GenericHandler)
    assert content.initialized
    assert content.content == b"hello"

    with freezegun.freeze_time(timezone.timedelta(minutes=1)):
        TestingStorage.set("foo", "bye")
        scanner.FileModifiedEvent("foo").commit(library)
        assert libraries_models.File.objects.count() == 1
        file.refresh_from_db()
        content = file.record.content_object
        assert isinstance(content, GenericHandler)
        assert content.content == b"bye"


@pytest.mark.django_db
def test_ignoring_directories(library: libraries_models.Library) -> None:
    """Directories with an ignore file are treated appropriately."""
    # Folders with a .nomedia file should be completely ignored.
    TestingStorage.set("foo/.nomedia", "")
    TestingStorage.set("foo/file.txt", "content")
    scanner.FileEvent("foo/file.txt").commit(library)
    assert not libraries_models.File.objects.exists()

    TestingStorage.set("bar/file.txt", "content")
    scanner.FileEvent("bar/file.txt").commit(library)
    file = libraries_models.File.objects.get()

    def refresh():
        del library.__dict__["_ignored_directories"]
        scanner.FileEvent("bar/file.txt").commit(library)
        assert libraries_models.File.objects.count() == 1
        file.refresh_from_db()

    # Make sure the already scanned file is marked unavailable when the folder gets a
    # .nomedia file...
    TestingStorage.set("bar/.nomedia", "")
    refresh()
    assert file.availability is None

    # ... and is available again once the .nomedia file is gone.
    TestingStorage.unset("bar/.nomedia")
    refresh()
    assert file.availability is not None
