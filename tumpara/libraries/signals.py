from __future__ import annotations

import collections
from typing import TYPE_CHECKING, Any, Literal, Optional, Protocol, TypeVar, Union, cast

from django import dispatch

if TYPE_CHECKING:
    from .models import Asset, Library

__all__ = ["new_file"]

_Asset = TypeVar("_Asset", bound="Asset", contravariant=True)


# This dictionary maps all known library context values to some object that doesn't
# change. The problem is that Django uses the id() of the sender to filter registered
# receivers. That works fine when the sender is a class or a model instance, but two
# Python strings with the same content don't necessarily need to be the same object.
# Therefor the new file signal might filter out receivers for some senders only because
# the id doesn't match, even though they are actually the same sender. We use this map
# to keep track of all the senders we know and make sure that equal strings actually
# get the same id.
# An alternative would have been to keep a asset of the strings and internalized them
# with sys.intern, but this works as well:
context_references = collections.defaultdict[Optional[str], Optional[object]](object)
context_references[None] = None


class NewFileReceiver(Protocol):
    def __call__(
        self, context: str, path: str, library: Library, **kwargs: Any
    ) -> Optional[Asset]:
        ...


class NewFileSignal(dispatch.Signal):
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
        result = super().send(
            sender=context_references[context],
            context=context,
            path=path,
            library=library,
        )
        return cast(list[tuple[NewFileReceiver, Optional[str]]], result)

    def send_robust(  # type: ignore
        self, context: str, path: str, library: Library
    ) -> list[tuple[NewFileReceiver, Union[Exception, str]]]:
        result = super().send_robust(
            sender=context_references[context],
            context=context,
            path=path,
            library=library,
        )
        return cast(list[tuple[NewFileReceiver, Union[Exception, str]]], result)


new_file = NewFileSignal()
"""Sent when a new file is found in a library.

When you register a receiver, it should use the provided parameters to decide if the new
file can (or should) be handled. Do this by returning a model instance to the
:class:`~tumpara.libraries.models.Asset` subclass that should handle the file. The file
will then be attached to that asset. You may also return an unsaved model instance, in
which case it will be saved.

If no receiver claims a file by returning a value other than ``None``, the new file will
be ignored. However, it is possible for more than one receiver to claim a file.

Note that this signal will *not* be called for new files that are copies of already
known files. In that case, the new file will be added to the existing
:class:`~tumpara.libraries.models.Asset` instead.

:param sender: The Library's ``context``.
:type sender: str
:param path: Path of the new file, relative to the library's root.
:type path: str
:param library: Library the file was found in.
:type library: ~tumpara.libraries.models.Library
:return: If the file cannot (or should not) be handled by the receiver, return ``None``.
    Otherwise return a model instance of the library
    :class:`tumpara.libraries.models.Asset` the file should be linked to.

:meta hide-value:
"""


class ScanFinishedReceiver:
    def __call__(
        self,
        sender: Literal["scan"],
        library: Library,
        **kwargs: Any,
    ) -> None:
        ...


class ScanFinishedSignal(dispatch.Signal):
    def connect(  # type: ignore
        self,
        receiver: ScanFinishedReceiver,
        sender: Optional[str] = None,
        weak: bool = True,
        dispatch_uid: Optional[str] = None,
    ) -> None:
        super().connect(receiver, sender, weak=weak, dispatch_uid=dispatch_uid)


scan_finished = dispatch.Signal()
"""Sent when a full library scan has finished.

:param sender: Currently the fixed string ``scan``.
:type sender: Literal["scan"]
:param library: The library that just finished scanning.
:type library: ~tumpara.libraries.models.Library
"""
