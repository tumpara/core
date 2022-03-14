import django.dispatch

__all__ = ["new_file", "files_changed"]

new_file = django.dispatch.Signal()
"""Sent when a new file is found in a library.

When you register a receiver, it should use the provided parameters to decide if the new
file can (or should) be handled. Do this by returning a model instance to the
:class:`~tumpara.libraries.models.Item` or its content object that should handle the
file. The file will then be attached to the library item. You may also return an unsaved
content object. In that case, a new item object will be created.

If no receiver claims a file by returning a value other than ``None``, the new file will
be ignored. If more than one receiver claims a file it will also be ignored.

:param sender: The Library's ``context``.
:type sender: str
:param path: Path of the new file, relative to the library's root.
:type path: str
:param library: Library the file was found in.
:type library: ~tumpara.libraries.models.Library
:return: If the file cannot (or should not) be handled by the receiver, return ``None``.
    Otherwise return a model instance for the file's content object.

:meta hide-value:
"""

files_changed = django.dispatch.Signal()
"""Sent when any of the files on record for a library item change.

:param sender: The type of content object in the library item.
:type sender: type[~django.db.models.Model]
:param item: Library item that had files changed.
:type item: ~tumpara.libraries.models.Item

:meta hide-value:
"""
