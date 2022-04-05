import os
import os.path

import hypothesis
import hypothesis.stateful
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from tumpara.libraries import models as libraries_models
from tumpara.testing import strategies as st

from .models import GenericHandler


class LibraryActionsStateMachine(hypothesis.stateful.RuleBasedStateMachine):
    """This is the base class for state-machine based integration tests for storages.

    The idea is that we repeatedly perform random actions on the backend (like creating
    files, moving stuff around, etc.) and store them. After each action, we have the
    library be rescanned. Then, we make sure that the state we have in the database
    matches that what we have in memory.

    To create a test based on this template, override the empty methods at the bottom
    that perform actual operations on the backend. For example, in case of the
    filesystem backend :meth:`_add_file` will create a new file on disk. Then create an
    invariant that looks something like this:

    .. code-block:: python

        @invariant()
        def perform_scan(self) -> None:
            self.library.scan(watch=False, thread_count=1, slow=False)
            self.assert_library_state(self.library)

    Note the use of :meth:`assert_library_state` to perform the actual tests.
    """

    def __init__(self) -> None:
        super().__init__()  # type: ignore

        # This set holds all directories that have been created (including the root).
        self.directories = {""}
        # Dictionary of the contents of all files that have been written. It will be
        # tested that the GenericFileHandler mapped it correctly.
        self.files = dict[str, bytes]()
        # Timestamps of when files have changed.
        self.file_timestamps = dict[str, timezone.datetime]()
        # Keep a list of events for debugging purposes.
        self.events = list[str]()

    @hypothesis.stateful.rule(
        filename=st.filenames(), content=st.binary(min_size=1), data=st.data()
    )
    def add_file(self, filename: str, content: bytes, data: st.DataObject) -> None:
        """Create a new file and write some content."""
        directory = data.draw(st.sampled_from(list(self.directories)))
        path = os.path.join(directory, filename)
        hypothesis.assume(path not in self.files)

        self.files[path] = content
        self.file_timestamps[path] = timezone.now()
        self.events.append(f"_add_file {path!r} {content!r}")
        self._add_file(path, content, data=data)

    @hypothesis.stateful.rule(name=st.directory_names(), data=st.data())
    def add_directory(self, name: str, data: st.DataObject) -> None:
        """Create an empty directory."""
        parent = data.draw(st.sampled_from(list(self.directories)))
        path = os.path.join(parent, name)
        hypothesis.assume(path not in self.directories)

        self.directories.add(path)
        self.events.append(f"_add_directory {path!r}")
        self._add_directory(path, data=data)

    @hypothesis.stateful.precondition(lambda self: len(self.files) >= 1)
    @hypothesis.stateful.rule(data=st.data())
    def delete_file(self, data: st.DataObject) -> None:
        """Delete a file."""
        path = data.draw(st.sampled_from(list(self.files.keys())))
        del self.files[path]
        del self.file_timestamps[path]
        self.events.append(f"_delete_file {path!r}")
        self._delete_file(path, data=data)

    @hypothesis.stateful.precondition(lambda self: len(self.directories) >= 2)
    @hypothesis.stateful.rule(data=st.data())
    def delete_directory(self, data: st.DataObject) -> None:
        """Delete a directory (and everything in it)."""
        path = data.draw(st.sampled_from([f for f in self.directories if f != ""]))
        path_with_slash = os.path.join(path, "")

        self.directories = {
            f
            for f in self.directories
            if f != path and not f.startswith(path_with_slash)
        }
        for file_path in list(self.files.keys()):
            if file_path.startswith(path_with_slash):
                del self.files[file_path]
                del self.file_timestamps[file_path]

        self.events.append(f"_delete_directory {path!r}")
        self._delete_directory(path, data=data)

    @hypothesis.stateful.precondition(
        lambda self: len(self.directories) >= 2 and len(self.files) >= 1
    )
    @hypothesis.stateful.rule(name=st.filenames(), data=st.data())
    def move_file(self, name: str, data: st.DataObject) -> None:
        """Move a file into another directory."""
        old_path = data.draw(st.sampled_from(list(self.files.keys())))
        old_directory = os.path.dirname(old_path)
        new_directory = data.draw(
            st.sampled_from([f for f in self.directories if f != old_directory])
        )
        new_path = os.path.join(new_directory, name)
        hypothesis.assume(new_path not in self.files)

        self.files[new_path] = self.files[old_path]
        self.file_timestamps[new_path] = self.file_timestamps[old_path]
        del self.files[old_path]
        del self.file_timestamps[old_path]

        self.events.append(f"_move_file {old_path!r} {new_path!r}")
        self._move_file(old_path, new_path, data=data)

    @hypothesis.stateful.precondition(lambda self: len(self.files) >= 1)
    @hypothesis.stateful.rule(content=st.binary(min_size=1), data=st.data())
    def change_file(self, content: bytes, data: st.DataObject) -> None:
        """Change the contents of a file."""
        path = data.draw(st.sampled_from(list(self.files.keys())))
        hypothesis.assume(content != self.files[path])
        self.files[path] = content
        self.file_timestamps[path] = timezone.now()
        self.events.append(f"_change_file {path!r} {content!r}")
        self._change_file(path, content, data=data)

    @hypothesis.stateful.precondition(lambda self: len(self.directories) >= 3)
    @hypothesis.stateful.rule(name=st.directory_names(), data=st.data())
    def move_directory(self, name: str, data: st.DataObject) -> None:
        old_path = data.draw(st.sampled_from([f for f in self.directories if f != ""]))
        parent = data.draw(
            st.sampled_from(
                [
                    f
                    for f in self.directories
                    if f not in [old_path]
                    and not f.startswith(os.path.join(old_path, ""))
                ]
            )
        )
        new_path = os.path.join(parent, name)
        hypothesis.assume(new_path not in self.directories)

        self.directories.remove(old_path)
        self.directories.add(new_path)
        old_path_slash = os.path.join(old_path, "")
        for directory_path in list(self.directories):
            if directory_path.startswith(old_path_slash):
                relative_directory_path = os.path.relpath(directory_path, old_path)
                self.directories.add(os.path.join(new_path, relative_directory_path))
                self.directories.remove(directory_path)

        for file_path in list(self.files.keys()):
            if file_path.startswith(old_path_slash):
                relative_file_path = os.path.relpath(file_path, old_path)
                new_file_path = os.path.join(new_path, relative_file_path)
                self.files[new_file_path] = self.files[file_path]
                self.file_timestamps[new_file_path] = self.file_timestamps[file_path]
                del self.files[file_path]
                del self.file_timestamps[file_path]

        self.events.append(f"_move_directory {old_path!r} {new_path!r}")
        self._move_directory(old_path, new_path, data=data)

    @hypothesis.stateful.precondition(lambda self: len(self.files) >= 2)
    @hypothesis.stateful.rule(data=st.data())
    def swap_files(self, data: st.DataObject) -> None:
        """Draw a list of file paths and move them around in a circle."""
        paths = data.draw(
            st.lists(
                st.sampled_from(list(self.files.keys())),
                min_size=2,
                max_size=len(self.files),
                unique=True,
            )
        )
        temp_path = data.draw(st.filenames(exclude=list(self.files.keys())))

        self.files[temp_path] = self.files[paths[0]]
        self.file_timestamps[temp_path] = self.file_timestamps[paths[0]]
        self._move_file(paths[0], temp_path, data=data)

        for i in range(1, len(paths)):
            self.files[paths[i - 1]] = self.files[paths[i]]
            self.file_timestamps[paths[i - 1]] = self.file_timestamps[paths[i]]
            self._move_file(paths[i], paths[i - 1], data=data)

        self.files[paths[-1]] = self.files[temp_path]
        self.file_timestamps[paths[-1]] = self.file_timestamps[temp_path]
        del self.files[temp_path]
        del self.file_timestamps[temp_path]
        self._move_file(temp_path, paths[-1], data=data)

    def assert_library_state(self, library: libraries_models.Library) -> None:
        """Helper method that asserts the state of a given library matches what is on
        record."""
        assert set(self.files.keys()) == set(self.file_timestamps.keys())
        file_queryset = libraries_models.File.objects.filter(
            record__library=library, availability__isnull=False
        )

        assert file_queryset.count() == len(self.files)
        for content in self.files.values():
            handler = GenericHandler.objects.get(content=content)
            assert handler.initialized
            record = libraries_models.Record.objects.get(
                content_type=ContentType.objects.get_for_model(handler),
                object_pk=handler.pk,
            )
            paths = {item[0] for item in self.files.items() if item[1] == content}
            assert record.files.filter(availability__isnull=False).count() == len(paths)
            for path in paths:
                file = record.files.get(availability__isnull=False, path=path)
                assert file.availability >= self.file_timestamps[path]

    def _add_file(self, path: str, content: bytes, data: st.DataObject) -> None:
        raise NotImplementedError("subclasses should override action methods")

    def _add_directory(self, path: str, data: st.DataObject) -> None:
        raise NotImplementedError("subclasses should override action methods")

    def _delete_file(self, path: str, data: st.DataObject) -> None:
        raise NotImplementedError("subclasses should override action methods")

    def _delete_directory(self, path: str, data: st.DataObject) -> None:
        raise NotImplementedError("subclasses should override action methods")

    def _move_file(self, old_path: str, new_path: str, data: st.DataObject) -> None:
        raise NotImplementedError("subclasses should override action methods")

    def _move_directory(
        self, old_path: str, new_path: str, data: st.DataObject
    ) -> None:
        raise NotImplementedError("subclasses should override action methods")

    def _change_file(self, path: str, content: bytes, data: st.DataObject) -> None:
        raise NotImplementedError("subclasses should override action methods")
