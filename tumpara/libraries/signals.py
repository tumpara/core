from __future__ import annotations

import collections
from typing import TYPE_CHECKING, Any, Optional, Protocol, TypeVar, Union

import django.dispatch

if TYPE_CHECKING:
    from .models import Library, Record

__all__ = ["new_file", "files_changed"]

_Record = TypeVar("_Record", bound="Record", contravariant=True)


# This dictionary maps all known library context values to some object that doesn't
# change. The problem is that Django uses the id() of the sender to filter registered
# receivers. That works fine when the sender is a class or a model instance, but two
# Python strings with the same content don't necessarily need to be the same object.
# Therefor the new file signal might filter out receivers for some senders only because
# the id doesn't match, even though they are actually the same sender. We use this map
# to keep track of all the senders we know and make sure that equal strings actually
# get the same id.
# An alternative would have been to keep a record of the strings and internalized them
# with sys.intern, but this works as well:
context_references = collections.defaultdict[Optional[str], Optional[object]](object)
context_references[None] = None


class NewFileReceiver(Protocol):
    def __call__(
        self, context: str, path: str, library: Library, **kwargs: Any
    ) -> Optional[Record]:
        ...


class NewFileSignal(django.dispatch.Signal):
    def connect(  # type: ignore
        self,
        receiver: NewFileReceiver,
        sender: Optional[str] = None,
        weak: bool = True,
        dispatch_uid: Optional[str] = None,
    ) -> None:
        super().connect(
            receiver, context_references[sender], weak=weak, dispatch_uid=dispatch_uid
        )

    def disconnect(  # type: ignore
        self,
        receiver: Optional[NewFileReceiver] = None,
        sender: Optional[str] = None,
        dispatch_uid: Optional[str] = None,
    ) -> bool:
        return super().disconnect(receiver, context_references[sender], dispatch_uid)

    def has_listeners(self, sender: Optional[str]) -> bool:  # type: ignore
        return super().has_listeners(context_references[sender])

    def send(  # type: ignore
        self, context: str, path: str, library: Library
    ) -> list[tuple[NewFileReceiver, Optional[str]]]:
        return super().send(
            sender=context_references[context],
            context=context,
            path=path,
            library=library,
        )

    def send_robust(  # type: ignore
        self, context: str, path: str, library: Library
    ) -> list[tuple[NewFileReceiver, Union[ValueError, str]]]:
        return super().send_robust(
            sender=context_references[context],
            context=context,
            path=path,
            library=library,
        )


new_file = NewFileSignal()
"""Sent when a new file is found in a library.

When you register a receiver, it should use the provided parameters to decide if the new
file can (or should) be handled. Do this by returning a model instance to the
:class:`~tumpara.libraries.models.Record` subclass that should handle the file. The file
will then be attached to that record. You may also return an unsaved record, in which
case it will be saved.

If no receiver claims a file by returning a value other than ``None``, the new file will
be ignored. If more than one receiver claims a file it will also be ignored.

Note that this signal will *not* be called for new files that are copies of already
known files. In that case, the new file will be added to the existing
:class:`tumpara.libraries.models.Record`.

:param sender: The Library's ``context``.
:type sender: str
:param path: Path of the new file, relative to the library's root.
:type path: str
:param library: Library the file was found in.
:type library: ~tumpara.libraries.models.Library
:return: If the file cannot (or should not) be handled by the receiver, return ``None``.
    Otherwise return a model instance of the library
    :class:`tumpara.libraries.models.Record` the file should be linked to.

:meta hide-value:
"""


class FilesChangedReceiver(Protocol[_Record]):
    def __call__(
        self,
        sender: type[_Record],
        record: _Record,
        **kwargs: Any,
    ) -> None:
        ...


class FilesChangedSignal(django.dispatch.Signal):
    def connect(  # type: ignore
        self,
        receiver: FilesChangedReceiver[Any],
        sender: Optional[type[Record]] = None,
        weak: bool = True,
        dispatch_uid: Optional[str] = None,
    ) -> None:
        super().connect(receiver, sender, weak=weak, dispatch_uid=dispatch_uid)


files_changed = FilesChangedSignal()
"""Sent when the list of files for a library record changes.

This happens when a new file has been scanned, an existing file is changed on disk or
a file is deleted. It is *not* sent when files are moved.

Receivers of this signal should check the files that are attached to the given library
record and act accordingly (for example by updating cached metadata). Should any of the
files no longer be applicable (for example if it has been edited and is now unreadable
or doesn't fit the library content object anymore) the
:class:`tumpara.libraries.models.File` object should be deleted.

:param sender: The type of library record.
:type sender: type[tumpara.libraries.models.Record]
:param record: Library record that had files changed.
:type record: ~tumpara.libraries.models.Record

:meta hide-value:
"""
