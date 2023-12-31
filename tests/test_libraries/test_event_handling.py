import datetime
import functools
import os.path
from collections.abc import Generator

import freezegun
import hypothesis.stateful
import pytest
from django.utils import timezone

from tumpara import testing
from tumpara.libraries import scanner
from tumpara.libraries.models import Asset, File, Library
from tumpara.testing import strategies as st

from .models import GenericHandler
from .storage import TestingStorage
from .utils import LibraryActionsStateMachine


@pytest.fixture
def library(
    patch_exception_handling: None,
) -> Generator[Library, None, None]:
    TestingStorage.clear()
    yield Library.objects.create(source="testing:///", context="test_storage")
    TestingStorage.clear()


@pytest.mark.django_db
def test_basic_file_scanning(library: Library, monkeypatch: pytest.MonkeyPatch) -> None:
    """New and modified file events work as expected."""
    TestingStorage.set("foo", "hello")
    scanner.FileEvent("foo").commit(library)
    # This will also make sure that there is *exactly* one file object.
    file = File.objects.get()
    assert file.library == library
    assert file.path == "foo"
    assert file.availability is not None
    asset = file.asset.resolve_instance()
    assert isinstance(asset, GenericHandler)
    assert asset.initialized
    assert asset.content == b"hello"

    with monkeypatch.context() as patch_context:
        patch_context.setattr(
            scanner.FileEvent,
            "__init__",
            functools.partial(pytest.fail, "unchanged file rescanned"),
        )
        scanner.FileModifiedEvent("foo").commit(library)

    with freezegun.freeze_time(datetime.timedelta(minutes=2)):
        TestingStorage.set("foo", "bye")
        scanner.FileModifiedEvent("foo").commit(library)
        file = File.objects.get()
        asset = file.asset.resolve_instance()
        assert isinstance(asset, GenericHandler)
        assert asset.content == b"bye"


@pytest.mark.django_db
def test_ignoring_directories(library: Library) -> None:
    """Directories with an ignore file are treated appropriately."""
    # Folders with a .nomedia file should be completely ignored.
    TestingStorage.set("foo/.nomedia", "")
    TestingStorage.set("foo/file.txt", "content")
    scanner.FileEvent("foo/file.txt").commit(library)
    assert not File.objects.exists()

    TestingStorage.set("bar/file.txt", "content")
    scanner.FileEvent("bar/file.txt").commit(library)
    file = File.objects.get()

    def refresh() -> None:
        del library.__dict__["_ignored_directories"]
        scanner.FileEvent("bar/file.txt").commit(library)
        assert File.objects.count() == 1
        file.refresh_from_db()

    # Make sure the already scanned file is marked unavailable when the directory gets a
    # new .nomedia file.
    TestingStorage.set("bar/.nomedia", "")
    refresh()
    assert file.availability is None

    # ... and is available again once the .nomedia file is gone.
    TestingStorage.unset("bar/.nomedia")
    refresh()
    assert file.availability is not None


@pytest.mark.django_db
def test_file_copying(library: Library) -> None:
    """A copied file (with the same content) is added to an existing asset object."""
    TestingStorage.set("foo", "content")
    TestingStorage.set("bar", "content")
    scanner.FileEvent("foo").commit(library)
    scanner.FileEvent("bar").commit(library)
    first_asset = Asset.objects.get()
    assert first_asset.files.filter(availability__isnull=False).count() == 2

    # Now add a new file, which we later edit so that it has the same content. It should
    # get its own asset the first time and then be moved into the other asset once
    # it's edited.
    TestingStorage.set("baz", "content2")
    scanner.FileEvent("baz").commit(library)
    second_asset = Asset.objects.exclude(pk=first_asset.pk).get()
    assert second_asset.files.filter(availability__isnull=False).count() == 1

    TestingStorage.set("baz", "content")
    scanner.FileEvent("baz").commit(library)
    assert first_asset.files.filter(availability__isnull=False).count() == 3
    assert second_asset.files.filter().count() == 1
    assert not second_asset.files.filter(availability__isnull=False).exists()

    # When moving back to the old content, the former file object should be marked as
    # available again.
    TestingStorage.set("baz", "content2")
    scanner.FileEvent("baz").commit(library)
    assert first_asset.files.filter().count() == 3
    assert first_asset.files.filter(availability__isnull=False).count() == 2
    assert second_asset.files.filter().count() == 1
    assert second_asset.files.filter(availability__isnull=False).count() == 1


@pytest.mark.django_db
def test_refinding_files(library: Library) -> None:
    """Files that were once present (but then no longer available) are re-found when
    they come back."""
    TestingStorage.set("foo", "foo")
    TestingStorage.set("bar", "bar")
    scanner.FileEvent("foo").commit(library)
    scanner.FileEvent("bar").commit(library)
    TestingStorage.unset("foo")
    TestingStorage.unset("bar")
    scanner.FileEvent("foo").commit(library)
    scanner.FileEvent("bar").commit(library)

    # Now we should have two files on asset, and both should be unavailable.
    assert File.objects.count() == 2
    foo_file = File.objects.get(path="foo")
    assert not foo_file.available
    bar_file = File.objects.get(path="bar")
    assert not bar_file.available
    bar_digest = bar_file.digest
    bar_asset = bar_file.asset.resolve_instance()
    assert isinstance(bar_asset, GenericHandler)
    assert bar_asset.content == b"bar"

    # Move the first file's content to a different location and add it back in.
    TestingStorage.set("foo2", "foo")
    scanner.FileEvent("foo2").commit(library)
    foo_file = File.objects.get(path="foo2")
    assert foo_file.available
    assert foo_file.path == "foo2"

    # Now add the second file back in, but with a new content.
    TestingStorage.set("bar", "whooo")
    scanner.FileEvent("bar").commit(library)
    bar_file = File.objects.get(path="bar")
    assert bar_file.available
    assert bar_file.digest != bar_digest
    bar_asset = bar_file.asset.resolve_instance()
    assert isinstance(bar_asset, GenericHandler)
    assert bar_asset.content == b"whooo"


@pytest.mark.django_db
def test_moving_and_deleting_file(library: Library) -> None:
    """Moved and deleted files are handled appropriately."""
    TestingStorage.set("foo", "content")
    scanner.FileEvent("foo").commit(library)
    TestingStorage.unset("foo")
    TestingStorage.set("bar", "content")
    scanner.FileMovedEvent("foo", "bar").commit(library)

    # Make sure we only have one file on asset (that's why we use .get()) and that the
    # path has been updated.
    file = File.objects.get()
    assert file.path == "bar"

    TestingStorage.unset("bar")
    scanner.FileRemovedEvent("bar").commit(library)
    assert File.objects.count() == 1
    file.refresh_from_db()
    assert file.available is False


@pytest.mark.django_db
def test_moving_and_deleting_directory(library: Library) -> None:
    """Moved and deleted directories are handled appropriately.

    This is more or less the same test as :func:`test_moving_and_deleting_file`.
    """
    for name in range(4):
        TestingStorage.set(f"foo/{name}", "content")
        scanner.FileEvent(f"foo/{name}").commit(library)
    for name in range(4):
        TestingStorage.unset(f"foo/{name}")
        TestingStorage.set(f"bar/{name}", "content")
    scanner.DirectoryMovedEvent("foo", "bar").commit(library)

    # Make sure the file assets have been reused and their paths are updated.
    files = list(File.objects.order_by("path"))
    assert len(files) == 4
    for name, file in enumerate(files):
        assert file.path == f"bar/{name}"

    for name in range(4):
        TestingStorage.unset(f"bar/{name}")
    scanner.DirectoryRemovedEvent("bar").commit(library)
    # Make sure there are still only four file objects and they are all unavailable.
    assert File.objects.count() == 4
    assert not File.objects.filter(availability__isnull=False).exists()


@pytest.mark.django_db
def test_moving_to_ignored_directories(library: Library) -> None:
    """Moving files and directories inside ignored directories marks those objects
    as unavailable."""
    TestingStorage.set("trash/.nomedia", "")
    for name in ("foo", "bar/a", "bar/b", "bar/c"):
        TestingStorage.set(name, "content")
        scanner.FileEvent(name).commit(library)

    TestingStorage.unset("foo")
    TestingStorage.set("trash/foo", "content")
    scanner.FileMovedEvent("foo", "trash/foo").commit(library)
    assert "foo" in File.objects.get(availability__isnull=True).path
    assert File.objects.filter(availability__isnull=False).count() == 3

    for name in ("bar/a", "bar/b", "bar/c"):
        TestingStorage.unset(name)
        TestingStorage.set(f"trash/{name}", "content")
    scanner.DirectoryMovedEvent("bar", "trash/bar").commit(library)
    assert File.objects.count() == 4
    assert not File.objects.filter(availability__isnull=False).exists()


@pytest.mark.django_db
def test_transparent_new_files(library: Library) -> None:
    """Modification and move events also work as expected when called with new file
    paths."""
    TestingStorage.set("foo", "content")
    TestingStorage.set("bar", "content")
    scanner.FileModifiedEvent("foo").commit(library)
    scanner.FileMovedEvent("something", "bar").commit(library)

    asset = Asset.objects.get()
    assert list(
        asset.files.order_by("path")
        .filter(availability__isnull=False)
        .values_list("path")
    ) == [("bar",), ("foo",)]


@pytest.mark.django_db
def test_moving_unavailable_objects(library: Library) -> None:
    """When moving a directory, unavailable objects should be moved as well."""
    TestingStorage.set("a/foo", "content")
    scanner.FileEvent("a/foo").commit(library)
    TestingStorage.set("a/bar", "content")
    scanner.FileEvent("a/bar").commit(library)
    TestingStorage.unset("a/bar")
    scanner.FileRemovedEvent("a/bar").commit(library)

    foo_file = File.objects.get(path="a/foo")
    bar_file = File.objects.get(path="a/bar")
    assert not bar_file.available

    TestingStorage.unset("a/foo")
    TestingStorage.set("b/foo", "content")
    scanner.DirectoryMovedEvent("a", "b").commit(library)

    foo_file.refresh_from_db()
    assert foo_file.path == "b/foo"
    assert foo_file.available
    bar_file.refresh_from_db()
    assert bar_file.path == "b/bar"
    assert not bar_file.available


@pytest.mark.slow
@pytest.mark.usefixtures("patch_exception_handling")
@testing.state_machine(use_django_executor=True)
class test_integration(LibraryActionsStateMachine):
    """State machine that tests individual event handling.

    This is an integration test that should handle most of the cases we have in the
    above tests as well. It also serves as a test for the testing storage.
    """

    def __init__(self) -> None:
        super().__init__()
        TestingStorage.clear()
        self.library = Library.objects.create(
            source=f"testing:///a", context="test_storage"
        )
        self.scanned_library = Library.objects.create(
            source=f"testing:///b", context="test_storage"
        )

    def teardown(self) -> None:
        TestingStorage.clear()

    def _add_file(self, path: str, content: bytes, data: st.DataObject) -> None:
        TestingStorage.set(path, content)

        # Randomly commit either a NewFileEvent or a FileModified event, as these
        # should both handle new files (in case of the latter because the file does
        # not exist in the database yet).
        if data.draw(st.booleans()):
            scanner.FileEvent(path).commit(self.library)
        else:
            scanner.FileModifiedEvent(path).commit(self.library)

    def _add_directory(self, path: str, data: st.DataObject) -> None:
        # There is no new directory event.
        pass

    def _delete_file(self, path: str, data: st.DataObject) -> None:
        TestingStorage.unset(path)

        scanner.FileRemovedEvent(path).commit(self.library)

    def _delete_directory(self, path: str, data: st.DataObject) -> None:
        prefix = os.path.join(path, "")
        for name in {
            name for name in TestingStorage.paths() if name.startswith(prefix)
        }:
            TestingStorage.unset(name)

        scanner.DirectoryRemovedEvent(path).commit(self.library)

    def _move_file(self, old_path: str, new_path: str, data: st.DataObject) -> None:
        TestingStorage.set(new_path, TestingStorage.get(old_path))
        TestingStorage.unset(old_path)

        scanner.FileMovedEvent(old_path, new_path).commit(self.library)

    def _move_directory(
        self, old_path: str, new_path: str, data: st.DataObject
    ) -> None:
        prefix = os.path.join(old_path, "")
        for name in {
            name for name in TestingStorage.paths() if name.startswith(prefix)
        }:
            new_name = os.path.join(new_path, os.path.relpath(name, old_path))
            TestingStorage.set(new_name, TestingStorage.get(name))
            TestingStorage.unset(name)

        scanner.DirectoryMovedEvent(old_path, new_path).commit(self.library)

    def _change_file(self, path: str, content: bytes, data: st.DataObject) -> None:
        TestingStorage.set(path, content)

        scanner.FileModifiedEvent(path).commit(self.library)

    @hypothesis.stateful.rule(data=st.data())
    def remove_untracked_file(self, data: st.DataObject) -> None:
        """Fire a file remove event for a file that is not tracked by the library."""
        path = data.draw(st.filenames(exclude=list(self.files.keys())))
        scanner.FileRemovedEvent(path).commit(self.library)

    @hypothesis.stateful.invariant()
    def check_state(self) -> None:
        self.assert_library_state(self.library)

        self.scanned_library.scan()
        self.assert_library_state(self.scanned_library)
