from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol

import django.dispatch
from django.db import models

if TYPE_CHECKING:
    from django.contrib.contenttypes import models as contenttypes_models

    from . import models as libraries_models

__all__ = ["new_file", "files_changed"]


class NewFileReceiver(Protocol):
    def __call__(
        self, sender: str, path: str, library: libraries_models.Library
    ) -> Optional[libraries_models.Record | models.Model]:
        ...


class NewFileSignal(django.dispatch.Signal):
    def connect(  # type: ignore
        self,
        receiver: NewFileReceiver,
        sender: Optional[str] = None,
        weak: bool = True,
        dispatch_uid: Optional[str] = None,
    ) -> None:
        super().connect(receiver, sender, weak=weak, dispatch_uid=dispatch_uid)


new_file = NewFileSignal()
"""Sent when a new file is found in a library.

When you register a receiver, it should use the provided parameters to decide if the new
file can (or should) be handled. Do this by returning a model instance to the
:class:`~tumpara.libraries.models.Record` or its content object that should handle the
file. The file will then be attached to the library record. You may also return an
unsaved content object. In that case, a new record object will be created.

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
    :class:`tumpara.libraries.models.Record` the file should be linked to. You may also
    return an instance of an another model type. It will be treated as the content
    object for a record, which will be created if it does not exist.

:meta hide-value:
"""


class FilesChangedReceiver(Protocol):
    def __call__(
        self, sender: contenttypes_models.ContentType, record: libraries_models.Record
    ) -> None:
        ...


class FilesChangedSignal(django.dispatch.Signal):
    def connect(  # type: ignore
        self,
        receiver: FilesChangedReceiver,
        sender: Optional[contenttypes_models.ContentType] = None,
        weak: bool = True,
        dispatch_uid: Optional[str] = None,
    ) -> None:
        super().connect(receiver, sender, weak=weak, dispatch_uid=dispatch_uid)


files_changed = FilesChangedSignal()
"""Sent when the list of files for a library record changes.

This happens when a new file has been scanned, an existing file is changed on disk or
a file is deleted.

Receivers of this signal should check the files that are attached to the given library
record and act accordingly (for example by updating cached metadata). Should any of the
files no longer be applicable (for example if it has been edited and is now unreadable
or doesn't fit the library content object anymore) the
:class:`tumpara.libraries.models.File` object should be deleted.

:param sender: The type of content object in the library record.
:type sender: django.contrib.contenttypes.models.ContentType
:param record: Library record that had files changed.
:type record: ~tumpara.libraries.models.Record

:meta hide-value:
"""
