import pytest

from tumpara.libraries import models as libraries_models

from .models import GenericHandler
from .storage import TestingStorage
from .test_event_handling import library  # noqa: F401


@pytest.mark.django_db
def test_file_creating(library: libraries_models.Library) -> None:
    TestingStorage.set("foo", "one")
    library.scan()
    file = libraries_models.File.objects.get()
    handler = GenericHandler.objects.get(content=b"one")
    assert file.record.content_object == handler

    TestingStorage.set("foo", "two")
    library.scan()
    file.refresh_from_db()
    handler = GenericHandler.objects.get(content=b"two")
    assert file.record.content_object == handler
    assert libraries_models.File.objects.count() == 1
    assert GenericHandler.objects.count() == 1
    assert GenericHandler.all_objects.count() == 2

    TestingStorage.set("bar", "three")
    library.scan()
    assert libraries_models.File.objects.count() == 2
    assert GenericHandler.objects.count() == 2
    assert GenericHandler.all_objects.count() == 3


@pytest.mark.django_db
def test_file_swapping(library: libraries_models.Library) -> None:
    """Swapping around two files should work."""
    TestingStorage.set("one", "foo")
    TestingStorage.set("two", "bar")
    library.scan()

    GenericHandler.assert_unique_contents()
    foo_handler = GenericHandler.objects.get(content=b"foo")
    assert foo_handler.records.filter(file__path="one").count() == 1
    bar_handler = GenericHandler.objects.get(content=b"bar")
    assert bar_handler.records.filter(file__path="two").count() == 1

    TestingStorage.set("two", "foo")
    TestingStorage.set("one", "bar")
    library.scan()

    GenericHandler.assert_unique_contents()
    assert foo_handler.records.filter(file__availability__isnull=False).count() == 1
    assert foo_handler.records.filter(file__path="two").exists()
    assert bar_handler.records.filter(file__availability__isnull=False).count() == 1
    assert bar_handler.records.filter(file__path="one").exists()


@pytest.mark.django_db
def test_complicated_swapping(library: libraries_models.Library) -> None:
    TestingStorage.set("foo", "content1")
    TestingStorage.set("bar", "content2")
    library.scan()

    TestingStorage.set("foo", "content2")
    TestingStorage.set("bar", "content1")
    library.scan()

    TestingStorage.set("baz", "content2")
    library.scan()

    TestingStorage.set("bar", "content2")
    TestingStorage.set("baz", "content1")
    library.scan()

    first_handler = GenericHandler.objects.get(content=b"content1")
    baz_file = first_handler.records.first().files.get(availability__isnull=False)
    assert baz_file.path == "baz"

    second_handler = GenericHandler.objects.get(content=b"content2")
    second_record = second_handler.records.first()
    assert second_record.files.filter(availability__isnull=False).count() == 2
    foo_file = second_record.files.get(availability__isnull=False, path="foo")
    bar_file = second_record.files.get(availability__isnull=False, path="bar")
    assert foo_file.digest == bar_file.digest


@pytest.mark.django_db
def test_record_splitting(library: libraries_models.Library) -> None:
    """The :func:`GenericHandler.handle_files_changed` handler correctly splits up a
    handler when the content of its files diverges."""
    TestingStorage.set("foo", "content1")
    TestingStorage.set("bar", "content1")
    library.scan()

    TestingStorage.set("bar", "content2")
    library.scan()

    assert GenericHandler.objects.count() == 2
    assert GenericHandler.objects.filter(content=b"content1").exists()
    assert GenericHandler.objects.filter(content=b"content2").exists()
