import django.dispatch

__all__ = ["new_file", "files_changed"]

new_file = django.dispatch.Signal()
"""Sent when a new file is found in a library.

When you register a receiver, it should use the provided parameters to decide if the new
file can (or should) be handled. Do this by returning a model instance to the
:class:`~tumpara.libraries.models.Record` or its content object that should handle the
file. The file will then be attached to the library record. You may also return an
unsaved content object. In that case, a new record object will be created.

If no receiver claims a file by returning a value other than ``None``, the new file will
be ignored. If more than one receiver claims a file it will also be ignored.

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

files_changed = django.dispatch.Signal()
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
