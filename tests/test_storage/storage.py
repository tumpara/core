import io
import os.path
import urllib.parse
from typing import ClassVar

from django.utils import timezone

from tumpara.libraries import storage


class TestingStorage(storage.LibraryStorage):
    """Library storage backend that looks up file contents from a dictionary.

    Use :meth:`set` to define file contents that will be returned.
    """

    _data: ClassVar[dict[str, tuple[timezone.datetime, bytes | str]]] = {}

    def __init__(self, parsed_uri: urllib.parse.ParseResult):
        pass

    def check(self) -> bool:
        return True

    def open(self, name: str, mode: str = "rb") -> io.BytesIO:
        assert (
            mode == "rb"
        ), "the testing backend only supports opening files with mode 'rb'"
        if name not in self._data:
            raise FileNotFoundError(f"file path {name!r} not found in dataset")
        _, content = self._data[name]
        if isinstance(content, str):
            return io.BytesIO(content.encode())
        else:
            return io.BytesIO(content)

    def get_modified_time(self, name: str) -> timezone.datetime:
        if name not in self._data:
            raise FileNotFoundError(f"file path {name!r} not found in dataset")
        return self._data[name][0]

    def exists(self, name: str) -> bool:
        return name in self._data

    def listdir(self, path: str) -> tuple[list[str], list[str]]:
        directories = set()
        files = set()

        for name in self._data:
            relpath = os.path.relpath(name, os.path.normpath(path))
            if relpath.startswith(".."):
                continue

            if os.path.dirname(relpath) == "":
                files.add(os.path.basename(relpath))
            else:
                directories.add(relpath.split("/")[0])

        return list(directories), list(files)

    @classmethod
    def set(cls, path: str, content: bytes | str) -> None:
        cls._data[path] = (timezone.now(), content)

    @classmethod
    def unset(cls, path: str) -> None:
        if path in cls._data:
            del cls._data[path]

    @classmethod
    def clear(cls) -> None:
        cls._data.clear()
