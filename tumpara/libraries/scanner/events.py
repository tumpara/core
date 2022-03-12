from __future__ import annotations

import abc
import dataclasses
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .. import models as libraries_models

_logger = logging.getLogger(__name__)


class Event(abc.ABC):
    """Base class for file events."""

    @abc.abstractmethod
    def commit(self, library: libraries_models.Library) -> None:
        """Handle this event for a given library."""


@dataclasses.dataclass
class NewFileEvent(Event):
    """Event for new files being created.

    This event is both for new files and for files that are moved into the library
    from outside.
    """

    path: str

    def commit(self, library: libraries_models.Library) -> None:
        ...


@dataclasses.dataclass
class FileModifiedEvent(Event):
    """Event for files being modified.

    When this event is created for a file that is not yet on record, it will be
    handled like a :class:`NewFileEvent`. The same will be done if the current file's
    type does not match the one on record (aka when the handler types are not the
    same).
    """

    path: str

    def commit(self, library: libraries_models.Library) -> None:
        ...


@dataclasses.dataclass
class FileMovedEvent(Event):
    """Event for files being renamed or moved while remaining inside the library."""

    # TODO This could be merged with FolderMovedEvent into a single MoveEvent with
    #  path prefixes as parameters.

    old_path: str
    new_path: str

    def commit(self, library: libraries_models.Library) -> None:
        ...


@dataclasses.dataclass
class FileRemovedEvent(Event):
    """Event for a file being deleted or moved outside the library."""

    path: str

    def commit(self, library: libraries_models.Library) -> None:
        ...


@dataclasses.dataclass
class FolderMovedEvent(Event):
    """Event for a folder being renamed or moved while remaining inside the library."""

    old_path: str
    new_path: str

    def commit(self, library: libraries_models.Library) -> None:
        ...


@dataclasses.dataclass
class FolderRemovedEvent(Event):
    """Event for a folder being deleted or moved outside the library."""

    path: str

    def commit(self, library: libraries_models.Library) -> None:
        ...
