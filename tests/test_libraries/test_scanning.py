import pytest

from tumpara.libraries.models import File, Library

from .models import GenericHandler
from .storage import TestingStorage
from .test_event_handling import library  # noqa: F401


@pytest.mark.django_db
def test_file_creating(library: Library) -> None:
    TestingStorage.set("foo", "one")
    library.scan()
    file = File.objects.get()
    handler = GenericHandler.objects.get(content=b"one")
    assert file.asset.resolve_instance() == handler

    TestingStorage.set("foo", "two")
    library.scan()
    file = File.objects.get()
    asset = GenericHandler.objects.get(content=b"two")
    assert file.asset.resolve_instance() == asset
    assert File.objects.count() == 1
    assert GenericHandler.objects.count() == 1
    assert GenericHandler.all_objects.count() == 2

    TestingStorage.set("bar", "three")
    library.scan()
    assert File.objects.count() == 2
    assert GenericHandler.objects.count() == 2
    assert GenericHandler.all_objects.count() == 3


@pytest.mark.django_db
def test_file_swapping(library: Library) -> None:
    """Swapping around two files should work."""
    TestingStorage.set("one", "foo")
    TestingStorage.set("two", "bar")
    library.scan()

    GenericHandler.assert_unique_contents()
    foo_asset = GenericHandler.objects.get(content=b"foo")
    bar_asset = GenericHandler.objects.get(content=b"bar")

    TestingStorage.set("two", "foo")
    TestingStorage.set("one", "bar")
    library.scan()

    GenericHandler.assert_unique_contents()
    assert foo_asset.files.filter(availability__isnull=False).count() == 1
    assert foo_asset.files.filter(path="two").exists()
    assert bar_asset.files.filter(availability__isnull=False).count() == 1
    assert bar_asset.files.filter(path="one").exists()


@pytest.mark.django_db
def test_complicated_swapping(library: Library) -> None:
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

    first_asset = GenericHandler.objects.get(content=b"content1")
    baz_file = first_asset.files.get(availability__isnull=False)
    assert baz_file.path == "baz"

    second_asset = GenericHandler.objects.get(content=b"content2")
    assert second_asset.files.filter(availability__isnull=False).count() == 2
    foo_file = second_asset.files.get(availability__isnull=False, path="foo")
    bar_file = second_asset.files.get(availability__isnull=False, path="bar")
    assert foo_file.digest == bar_file.digest


@pytest.mark.django_db
def test_asset_splitting(library: Library) -> None:
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


@pytest.mark.django_db
def test_more_swapping(library: Library) -> None:
    TestingStorage.set("one", "foo")
    TestingStorage.set("two", "bar")
    library.scan()

    TestingStorage.set("one", "bar")
    TestingStorage.set("two", "foo")
    library.scan()

    TestingStorage.set("one", "foo")
    TestingStorage.set("two", "bar")
    library.scan()

    foo_asset = GenericHandler.objects.get(content=b"foo")
    assert foo_asset.files.filter(availability__isnull=False).count() == 1
    foo_asset.files.get(availability__isnull=False, path="one")
    bar_asset = GenericHandler.objects.get(content=b"bar")
    assert bar_asset.files.filter(availability__isnull=False).count() == 1
    bar_asset.files.get(availability__isnull=False, path="two")


@pytest.mark.django_db
def test_moving(library: Library) -> None:
    TestingStorage.set("a", "foo")
    TestingStorage.set("b", "bar")
    library.scan()

    TestingStorage.set("directory/b", "bar")
    TestingStorage.unset("b")
    library.scan()
