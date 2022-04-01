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
    """New and modified file events work as expected."""
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


@pytest.mark.django_db
def test_file_copying(library: libraries_models.Library) -> None:
    """A copied file (with the same content) is added to an existing record object."""
    TestingStorage.set("foo", "content")
    TestingStorage.set("bar", "content")
    scanner.FileEvent("foo").commit(library)
    scanner.FileEvent("bar").commit(library)
    first_record = libraries_models.Record.objects.get()
    assert first_record.files.filter(availability__isnull=False).count() == 2

    # Now add a new file, which we later edit so that it has the same content. It should
    # get its own record the first time and then be moved into the other record once
    # it's edited.
    TestingStorage.set("baz", "content2")
    scanner.FileEvent("baz").commit(library)
    second_record = libraries_models.Record.objects.exclude(pk=first_record.pk).get()
    assert second_record.files.filter(availability__isnull=False).count() == 1

    TestingStorage.set("baz", "content")
    scanner.FileEvent("baz").commit(library)
    assert first_record.files.filter(availability__isnull=False).count() == 3
    assert second_record.files.filter().count() == 1
    assert not second_record.files.filter(availability__isnull=False).exists()


@pytest.mark.django_db
def test_file_unification(library: libraries_models.Library) -> None:
    """When a file is edited in such a way that it becomes a copy of an existing file,
    they are merged into the same library record."""
