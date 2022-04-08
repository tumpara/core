import abc
import collections
import os
import re
import urllib.parse
from collections.abc import Callable, Generator
from typing import Literal, Optional, overload

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files import storage as django_storage

from .. import scanner

WatchGenerator = Generator[Optional[scanner.Event], Literal[None, False] | int, None]


class LibraryStorage(django_storage.Storage, abc.ABC):
    """Base class for storage backends used by :class:`tumpara.storage.models.Library`.

    This is a refinement of Django's storage engine, providing additional methods
    related to scanning.

    Storage objects are created from a URI. Instances of this class receive the parsed
    URI object (:class:`urllib.parse.ParseResult`) in the constructor. A storage
    implementation may use all other aspects of the URI to identify how to connect to
    the storage. Some backends may also require additional information in the form of
    query parameters.
    """

    @abc.abstractmethod
    def __init__(self, parsed_uri: urllib.parse.ParseResult):
        """Initialize the backend.

        :param parsed_uri: The parsed source URI of the library.
        """

    @abc.abstractmethod
    def check(self) -> None:
        """Check the backend's configuration and return whether it is valid and usable.

        :raises ValidationError: When the backend is misconfigured or the
            remote service cannot be reached (if applicable).
        """

    def walk_files(
        self, start_directory: str = "", *, safe: bool = True
    ) -> Generator[str, None, None]:
        """Generator that yields the paths of all files in this storage.

        The default implementation recursively iterates through all directories and
        yields filenames appropriately. Override this method if other storage system
        provide a more efficient way of doing this.

        :param start_directory: Optional starting directory. Set this to anything other
            than an empty string to only iterate over a subdirectory.
        :param safe: Set this to ``False`` to re-raise encountered IO errors. Otherwise,
            they will be dropped silently.
        """
        if not isinstance(start_directory, str):
            raise TypeError("Expected a string as the starting directory.")
        paths = collections.deque([start_directory])

        while len(paths) > 0:
            current_path = paths.pop()

            try:
                directories, files = self.listdir(current_path)
            except IOError:  # pragma: no cover
                if safe:
                    continue
                else:
                    raise

            paths.extend(
                os.path.join(current_path, directory) for directory in directories
            )
            for filename in files:
                yield os.path.join(current_path, filename)

    def watch(
        self,
    ) -> WatchGenerator:
        """Generator that yields events on changes.

        Instead of just iterating over the generator, you can also send a timeout (in
        seconds). When no events are received in that time, the generator will yield
        ``None`` in that iteration. This can be helpful when watching multiple storages
        at the same time.

        For various reasons (for example when the timeout runs out without yielding any
        new events), the generator may also yield ``None`` from time to time. Consumers
        should just ignore these results.

        Send `False` to this generator to stop watching and close the generator.

        :raises NotImplementedError: This may not be supported by all backends. If
            watching is unsupported, this exception will be raised.
        """
        raise NotImplementedError(
            "This library backend does not support watching files."
        )


class LibraryStorageManager:
    """Management interface that holds all supported storage backends."""

    def __init__(self) -> None:
        self.schemes = dict[str, type[LibraryStorage]]()

    @overload
    def register(
        self, scheme: str
    ) -> Callable[[type[LibraryStorage]], type[LibraryStorage]]:
        ...

    @overload
    def register(self, scheme: str, storage_class: type[LibraryStorage]) -> None:
        ...

    def register(
        self, scheme: str, storage_class: Optional[type[LibraryStorage]] = None
    ) -> Optional[Callable[[type[LibraryStorage]], type[LibraryStorage]]]:
        """Register a backend with the store.

        Use this as a decorator on the class:

        .. code-block:: python

            from tumpara.libraries import storage

            @storage.register("unicorn")
            class UnicornStorage(storage.LibraryStorage):
                ...  # Implement unicorn-based storage here.

        You may add the decorator multiple times for more than one supported scheme.
        For example, that might be the case when both unencrypted and encrypted
        connections are supported.

        Alternatively, you can also call this method (without using it as a decorator)
        and pass the storage class as the second argument. This is useful for placing
        inside the :meth:`~django.apps.AppConfig.ready` method of an application
        configuration class.

        :param scheme: The scheme part of all URIs supported by the backend.
        :param storage_class: Storage class to register as a backend. If this is not
            provided, decorator will be returned.
        """
        assert (
            isinstance(scheme, str) and len(scheme) > 0
        ), "cannot register library storage backend with an empty scheme"
        assert re.search(
            r"^[a-zA-Z]([a-zA-Z0-9$\-_@.&!*\"'(),]|%[0-9a-fA-F]{2})*$", scheme
        ), f"library storage backend scheme is invalid: {scheme}"

        def decorate_class(storage_class: type[LibraryStorage]) -> type[LibraryStorage]:
            assert issubclass(
                storage_class, LibraryStorage
            ), "library storage backends must be subclasses of LibraryStorage"
            if scheme in self.schemes:
                raise ImproperlyConfigured(
                    f"cannot register more than one library storage backend for the "
                    f"scheme {scheme!r}"
                )

            self.schemes[scheme] = storage_class
            return storage_class

        if storage_class is not None:
            decorate_class(storage_class)
            return None
        else:
            return decorate_class

    def build(self, uri: str) -> LibraryStorage:
        """Parse the given URI and return an instance of the corresponding backend."""
        parsed_uri = urllib.parse.urlparse(uri)
        scheme = parsed_uri.scheme
        if scheme not in self.schemes:
            raise ValidationError(
                f"no supported library storage backend found for scheme {scheme!r}"
            )
        return self.schemes[scheme](parsed_uri)


backends = LibraryStorageManager()
