"""Test cases for the file system backend.

Only the functionality provided by the backend is tested here, everything that
comes from Django's storage API is ignored. The main thing we want to test here is that
the correct events are emitted in different situations.
"""

import os
from urllib.parse import urlparse

import hypothesis
import hypothesis.control
import pytest
from django.core.exceptions import ValidationError

from tumpara.libraries import scanner
from tumpara.libraries.storage.base import WatchGenerator
from tumpara.libraries.storage.file import FileSystemBackend
from tumpara.testing import strategies as st

Context = tuple[str, list[str], list[str], FileSystemBackend]
WatchContext = tuple[str, list[str], list[str], FileSystemBackend, WatchGenerator]


@st.composite
def contexts(draw: st.DrawFn) -> Context:
    """Build an environment for testing the filesystem backend.

    This will generate a random directory structure (including file contents). It will
    also actually mirror that structure on disk in a temporary directory.
    """
    library_base = draw(st.temporary_directories())
    directories, file_paths, file_contents = draw(st.directory_trees())

    for path in directories[1:]:
        os.mkdir(os.path.join(library_base, path))
    for i in range(len(file_paths)):
        with open(os.path.join(library_base, file_paths[i]), "w") as f:
            f.write(file_contents[i])

    backend = FileSystemBackend(urlparse(f"file://{library_base}"))
    return library_base, directories, file_paths, backend


@st.composite
def watch_contexts(draw: st.DrawFn) -> WatchContext:
    library_base, directories, file_paths, backend = draw(contexts())
    generator = backend.watch()
    # We need to get one item from the generator to get it going, since the
    # initialization code isn't actually run until we collect an item. The filesystem
    # backend explicitly sends an always-None response first for this.
    assert next(generator) is None

    @hypothesis.control.cleanup
    def teardown_backend_watch() -> None:
        try:
            generator.send(False)
        except (StopIteration, TypeError):
            pass

    return library_base, directories, file_paths, backend, generator


base_settings = hypothesis.settings(
    max_examples=15,
    suppress_health_check=(
        hypothesis.HealthCheck.too_slow,
        hypothesis.HealthCheck.data_too_large,
    ),
)


@hypothesis.settings(max_examples=1)
@hypothesis.given(st.temporary_directories())
def test_check(path: str) -> None:
    """Backend raises errors when an invalid path is specified."""
    FileSystemBackend(urlparse(f"file://{path}")).check()

    with pytest.raises(ValidationError, match="does not exist"):
        FileSystemBackend(urlparse(f"file://{path}/invalid")).check()

    with open(f"{path}/file", "w") as f:
        f.write("Hello")

    with pytest.raises(ValidationError, match="is not a directory"):
        FileSystemBackend(urlparse(f"file://{path}/file")).check()


@base_settings
@hypothesis.given(contexts())
def test_walk_files(context: Context) -> None:
    """Walking files in the backend works as expected."""
    library_base, _, files, backend = context
    paths = list(backend.walk_files())

    paths_set = set(paths)
    files_set = set(files)
    assert paths_set == files_set


@base_settings
@hypothesis.given(watch_contexts(), st.data())
def test_watch_file_edits(context: WatchContext, data: st.DataObject) -> None:
    """Events emitted from file edits are the correct FileModifiedEvent objects."""
    library_base, _, files, backend, generator = context

    for path in data.draw(st.sets(st.sampled_from(files), min_size=2, max_size=6)):
        with open(os.path.join(library_base, path), "a") as f:
            f.write(data.draw(st.text(min_size=10)))
        event = next(generator)
        assert isinstance(event, scanner.FileModifiedEvent)
        assert event.path == path

    assert generator.send("check_empty") is True  # type: ignore


@base_settings
@hypothesis.given(watch_contexts(), st.temporary_directories(), st.data())
def test_watch_file_removal(
    context: WatchContext, secondary_base: str, data: st.DataObject
) -> None:
    """Events emitted when files are deleted or moved outside of the library are
    the correct FileRemovedEvent objects.
    """
    library_base, _, files, backend, generator = context

    removed_files = data.draw(st.sets(st.sampled_from(files), min_size=2, max_size=6))
    for index, path in enumerate(removed_files):
        # Take turns deleting stuff and moving it out of the library. Both actions
        # should yield the same event.
        if index % 2 == 0:
            os.remove(os.path.join(library_base, path))
        else:
            os.rename(
                os.path.join(library_base, path),
                os.path.join(secondary_base, str(index)),
            )
        event = next(generator)
        assert isinstance(event, scanner.FileRemovedEvent)
        assert event.path == path

    assert generator.send("check_empty") is True  # type: ignore


@base_settings
@hypothesis.given(watch_contexts(), st.temporary_directories(), st.data())
def test_watch_directory_moving(
    context: WatchContext, secondary_base: str, data: st.DataObject
) -> None:
    """Events emitted when directories are moved in and out of the library are the
    correct :class:`scanner.FileEvent` and :class:`DirectoryRemovedEvent` objects.
    """
    library_base, directories, files, backend, generator = context

    new_directory = data.draw(st.directory_names(exclude=directories))
    new_files = data.draw(st.sets(st.filenames(), min_size=2, max_size=6))

    # Create a new directory outside and move it inside the library. This should yield a
    # FileEvent for each new file.
    os.mkdir(os.path.join(secondary_base, new_directory))
    for filename in new_files:
        with open(os.path.join(secondary_base, new_directory, filename), "w") as f:
            f.write(data.draw(st.text()))
    os.rename(
        os.path.join(secondary_base, new_directory),
        os.path.join(library_base, new_directory),
    )
    # Prepend the new folder path to the filenames to make them paths relative to
    # the library root.
    new_files = {os.path.join(new_directory, path) for path in new_files}
    # Check that all events are present.
    for event in [next(generator) for _ in range(len(new_files))]:
        assert isinstance(event, scanner.FileEvent)
        assert event.path in new_files
        new_files.remove(event.path)
    assert len(new_files) == 0

    # Move the folder outside of the library again. This should yield a
    # FolderRemovedEvent.
    os.rename(
        os.path.join(library_base, new_directory),
        os.path.join(secondary_base, new_directory),
    )
    event = next(generator)
    assert isinstance(event, scanner.DirectoryRemovedEvent)
    assert event.path == new_directory

    assert generator.send("check_empty") is True  # type: ignore


@base_settings
@hypothesis.given(watch_contexts(), st.data())
def test_watch_moving_inside(context: WatchContext, data: st.DataObject) -> None:
    """Events emitted when files and directories are moved inside the library are
    correct.
    """
    library_base, directories, files, backend, generator = context

    source_file = data.draw(st.sampled_from(files))
    target_directory = data.draw(st.sampled_from(directories))
    new_filename = data.draw(st.filenames(exclude=files))
    os.rename(
        os.path.join(library_base, source_file),
        os.path.join(library_base, target_directory, new_filename),
    )
    event = next(generator)
    assert isinstance(event, scanner.FileMovedEvent)
    assert event.old_path == source_file
    assert event.new_path == os.path.join(target_directory, new_filename)

    source_directory = data.draw(st.sampled_from(directories[1:]))
    new_directory = data.draw(st.directory_names(exclude=directories))
    os.rename(
        os.path.join(library_base, source_directory),
        os.path.join(library_base, new_directory),
    )
    event = next(generator)
    assert isinstance(event, scanner.DirectoryMovedEvent)
    assert event.old_path == source_directory
    assert event.new_path == new_directory

    assert generator.send("check_empty") is True  # type: ignore


@base_settings
@hypothesis.given(watch_contexts(), st.temporary_directories(), st.data())
def test_watch_creation(
    context: WatchContext, secondary_base: str, data: st.DataObject
) -> None:
    """Events emitted when files are created in the library or moved into the
    library from outside are the correct NewFileEvent objects."""
    library_base, directories, files, _, generator = context

    new_files = data.draw(st.sets(st.filenames(exclude=files), min_size=2, max_size=6))

    def create_file(path: str) -> None:
        with open(path, "w") as f:
            f.write(data.draw(st.text()))

    for index, filename in enumerate(new_files):
        # Take turns creating new stuff in the library and moving it in from outside.
        # Both actions should yield the same event.
        library_path = os.path.join(data.draw(st.sampled_from(directories)), filename)
        absolute_path = os.path.join(library_base, library_path)
        if index % 2 == 0:
            create_file(absolute_path)
        else:
            tmp_path = os.path.join(secondary_base, "tmp")
            create_file(tmp_path)
            os.rename(tmp_path, absolute_path)

        event = next(generator)
        assert isinstance(event, scanner.FileEvent)
        assert event.path == library_path

    assert generator.send("check_empty") is True  # type: ignore
