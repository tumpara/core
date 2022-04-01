from __future__ import annotations

import abc
import dataclasses
import hashlib
import logging
import os.path
import re
from typing import TYPE_CHECKING, cast

from django.db import models, transaction
from django.utils import timezone

from .. import signals as libraries_signals

if TYPE_CHECKING:
    from .. import models as libraries_models

_logger = logging.getLogger(__name__)


class Event(abc.ABC):
    """Base class for file events."""

    @abc.abstractmethod
    def commit(self, library: libraries_models.Library) -> None:
        """Handle this event for a given library.

        :param library: The library to apply changed to.
        :param slow: If this is enabled,
        """


@dataclasses.dataclass
class FileEvent(Event):
    """Generic event for scanning a file path.

    This event is used for:

    - New files
    - Files moved in from outside the library
    - Unignored files (where the parent directory is no longer ignored)
    - Other situations where no other event is available.
    """

    path: str

    @transaction.atomic
    def commit(self, library: libraries_models.Library) -> None:
        from django.contrib.contenttypes.models import ContentType

        from .. import models as libraries_models

        if library.check_path_ignored(self.path):
            _logger.debug(
                f"New file {self.path!r} in {library} - skipping because the file is "
                f"in an ignored directory."
            )
            libraries_models.File.objects.filter(
                path=self.path, record__library=library
            ).update(availability=None)
            return

        hasher = hashlib.blake2b(digest_size=32)
        with library.storage.open(self.path, "rb") as content:
            hasher.update(content.read())
        digest = hasher.hexdigest()

        # Fetch a list of existing records that might match this file.
        file_candidates = list(
            libraries_models.File.objects.filter(
                models.Q(path=self.path) | models.Q(digest=digest),
                record__library=library,
            )
        )

        done = False

        # If this new file's digest matches one of the files we already have on record,
        # This might mean that the file is unchanged. It might also mean that the new
        # file is a copy  of something we already have on record.
        for file in file_candidates:
            if file.digest == digest:
                if file.path == self.path:
                    # The file is unchanged, so we are done here.
                    file.availability = timezone.now()
                    file.save()
                    return

                # First, check if an existing file object for this path exists. If that
                # is already attached to the same record as we have here, we are done.
                for other_file in file_candidates:
                    if (
                        other_file is not file
                        and other_file.path == self.path
                        and other_file.record == file.record
                        and other_file.availability is not None
                    ):
                        return

                file.record.files.create(
                    # Note that we will definitely be creating a record with a unique
                    # path inside the library here, because otherwise we would have
                    # caught it in the earlier case.
                    path=self.path,
                    digest=digest,
                    availability=timezone.now(),
                )
                libraries_signals.files_changed.send_robust(
                    sender=file.record.content_type.model_class(), record=file.record
                )

                # Go through the other candidates with the same path and mark them
                # unavailable (otherwise we might get duplicate records for the same
                # path).
                for other_file in file_candidates:
                    if other_file is not file and other_file.path == self.path:
                        other_file.availability = None
                        other_file.save()
                        pass

                return

        # If we already have a matching record for the file, we can use that. By
        # assumption, such an entry will be unique.
        for file in file_candidates:
            if file.path == self.path and file.availability is not None:
                if done:
                    # Make sure we still only have at most one available file for a path
                    # in the library.
                    file.availability = None
                    file.save()
                    continue

                file.availability = timezone.now()
                changed = False
                if file.digest != digest:
                    file.digest = digest
                    changed = True
                file.save()

                if changed:
                    libraries_signals.files_changed.send_robust(
                        sender=file.record.content_type.model_class(),
                        record=file.record,
                    )
                done = True
        if done:
            return

        # Since we didn't find a matching record in the last step, we go on and check
        # for any old records that are currently unavailable but fit the description for
        # our file. This step is important because it covers files that were renamed /
        # moved as well as files that were edited.
        for file in file_candidates:
            if (
                (file.path == self.path or file.digest == digest)
                # This time we explicitly want unavailable records:
                and file.availability is None
            ):
                file.path = self.path
                file.digest = digest
                file.availability = timezone.now()
                file.save()
                libraries_signals.files_changed.send_robust(
                    sender=file.record.content_type.model_class(), record=file.record
                )
                return

        # Since we couldn't place the file into any existing library record, we can now
        # create a new one. To do that, we ask all the registered receivers of the
        # `new_file` signal to see if we find some content object that is willing to
        # take the file (see the signal's documentation for details).
        result = libraries_signals.new_file.send_robust(
            sender=library.context,
            path=self.path,
            library=library,
        )
        responses = [
            cast(libraries_models.Record | models.Model, response)
            for _, response in result
            if isinstance(response, models.Model)
        ]
        if len(responses) == 0:
            _logger.debug(
                f"New file {self.path!r} in {library} - skipping because no "
                f"compatible file handler was found."
            )
            return
        elif len(responses) > 1:
            _logger.warning(
                f"New file {self.path!r} in {library} - skipping because more than one "
                f"compatible file handler was found."
            )
            return
        else:
            response = responses[0]
            if isinstance(response, libraries_models.Record):
                record = response
            else:
                # This is the case where we got a content object from the signal
                # receiver (which may be unsaved). In that case, create (or find) a
                # record for it.
                if response._state.adding:
                    response.save()
                record, _ = libraries_models.Record.objects.get_or_create(
                    library=library,
                    content_type=ContentType.objects.get_for_model(response),
                    object_pk=response.pk,
                )

            record.files.create(
                path=self.path,
                digest=digest,
                availability=timezone.now(),
            )
            libraries_signals.files_changed.send_robust(
                sender=record.content_type.model_class(), record=record
            )


@dataclasses.dataclass
class FileModifiedEvent(Event):
    """Event for files being modified.

    When this event is created for a file that is not yet on record, it will be
    handled like a new file.
    """

    path: str

    def commit(self, library: libraries_models.Library) -> None:
        from .. import models as libraries_models

        try:
            file = libraries_models.File.objects.get(
                record__library=library,
                path=self.path,
                availability__isnull=False,
            )
        except libraries_models.File.DoesNotExist:
            _logger.debug(
                f"Got a file modified event for {self.path!r} in {library} which is "
                f"not on record. Handling as a new file."
            )
            FileEvent(path=self.path).commit(library)
            return

        if library.check_path_ignored(self.path):
            file.availability = None
            file.save()
            _logger.debug(
                f"Got a file modified event for {self.path!r} in {library}, which is "
                f"in an ignored directory. The file was marked unavailable."
            )
            return

        if (
            file.availability is not None
            and file.availability > library.storage.get_modified_time(self.path)
        ):
            # The file seems to still be available and hasn't changed since the last
            # time we checked, so go ahead and call it a day.
            return
        else:
            # Since the file was changed, we need to rescan it.
            FileEvent(path=self.path).commit(library)


@dataclasses.dataclass
class FileMovedEvent(Event):
    """Event for files being renamed or moved while remaining inside the library."""

    # TODO This could be merged with DirectoryMovedEvent into a single MoveEvent with
    #  path prefixes as parameters.

    old_path: str
    new_path: str

    def commit(self, library: libraries_models.Library) -> None:
        from .. import models as libraries_models

        file_queryset = libraries_models.File.objects.filter(
            record__library=library, path=self.old_path, availability__isnull=False
        )
        touched_records = libraries_models.Record.objects.filter(
            file__in=file_queryset
        ).distinct()

        if library.check_path_ignored(self.new_path):
            affected_rows = file_queryset.update(availability=None)
            _logger.debug(
                f"Moving file {self.old_path!r} to {self.new_path!r}, but the new path "
                f"is in an ignored directory. Records were marked unavailable."
            )
        else:
            affected_rows = file_queryset.update(path=self.new_path)
            if affected_rows == 0:
                _logger.debug(
                    f"Got a file moved event for {self.old_path!r} to "
                    f"{self.new_path!r} in {library}, but no direct record was "
                    f"available. Handling as a new file."
                )
                FileEvent(path=self.new_path).commit(library)
            else:
                _logger.debug(
                    f"Moved {self.old_path!r} to {self.new_path!r} in {library}."
                )

        if affected_rows > 1:
            _logger.warning(
                "More than one file processed for file move event which should "
                "have been unique."
            )
        for record in touched_records:
            libraries_signals.files_changed.send_robust(
                sender=record.content_type.model_class(), record=record
            )


@dataclasses.dataclass
class FileRemovedEvent(Event):
    """Event for a file being deleted or moved outside the library."""

    path: str

    def commit(self, library: libraries_models.Library) -> None:
        from .. import models as libraries_models

        file_queryset = libraries_models.File.objects.filter(
            record__library=library, path=self.path, availability__isnull=False
        )
        touched_records = libraries_models.Record.objects.filter(
            file__in=file_queryset
        ).distinct()

        affected_rows = file_queryset.update(availability=None)
        if affected_rows == 0:
            _logger.debug(
                f"Got a file removed event for {self.path!r} in {library}, but no "
                f"record was available."
            )
        else:
            if affected_rows > 1:
                _logger.warning(
                    "More than one file processed for file remove event which should "
                    "have been unique."
                )
            _logger.debug(f"Removed {self.path} in {library}.")

        for record in touched_records:
            libraries_signals.files_changed.send_robust(
                sender=record.content_type.model_class(), record=record
            )


@dataclasses.dataclass
class DirectoryMovedEvent(Event):
    """Event for a directory being renamed or moved while remaining inside the library."""

    old_path: str
    new_path: str

    def commit(self, library: libraries_models.Library) -> None:
        from .. import models as libraries_models

        # The path.join stuff adds an additional slash at the end, making sure really
        # only files inside of the directory are targeted (not that other records should
        # exist, but better safe than sorry). Also, we use regex here because SQLite
        # doesn't support case-sensitive startswith.
        # TODO: Check if we have a case-insensitive filesystem.
        path_regex = "^" + re.escape(os.path.join(self.old_path, ""))

        # We intentionally don't filter out unavailable files so they are moved along
        # with the other files in the directory. Yay, ghosts :)
        file_queryset = libraries_models.File.objects.filter(
            record__library=library, path__regex=path_regex
        )
        touched_records = libraries_models.Record.objects.filter(
            file__in=file_queryset
        ).distinct()

        if library.check_path_ignored(self.new_path):
            affected_rows = file_queryset.update(availability=None)
            _logger.debug(
                f"Moving directory {self.old_path!r} to {self.new_path!r}, but the new "
                f"path is in an ignored directory. {affected_rows} records were marked "
                f"unavailable."
            )
        else:
            count = 0
            for file in file_queryset:
                file.path = os.path.join(
                    self.new_path, os.path.relpath(file.path, self.old_path)
                )
                file.save()
                count += 1
            _logger.debug(
                f"Got a directory moved event from {self.old_path!r} to "
                f"{self.new_path!r} in {library} which affected {count} file(s)."
            )

        for record in touched_records:
            libraries_signals.files_changed.send_robust(
                sender=record.content_type.model_class(), record=record
            )


@dataclasses.dataclass
class DirectoryRemovedEvent(Event):
    """Event for a directory being deleted or moved outside the library."""

    path: str

    def commit(self, library: libraries_models.Library) -> None:
        from .. import models as libraries_models

        # As before, use regex instead of startswith because SQLite doesn't support the
        # latter case-sensitively.
        # TODO: Check if we have a case-insensitive filesystem.
        path_regex = "^" + re.escape(os.path.join(self.path, ""))

        file_queryset = libraries_models.File.objects.filter(
            record__library=library, path__regex=path_regex, availability__isnull=False
        )
        touched_records = libraries_models.Record.objects.filter(
            file__in=file_queryset
        ).distinct()

        affected_rows = file_queryset.update(availability=None)
        _logger.debug(
            f"Got a directory removed event for {self.path!r} in {library} which "
            f"affected {affected_rows} file(s)."
        )

        for record in touched_records:
            libraries_signals.files_changed.send_robust(
                sender=record.content_type.model_class(), record=record
            )
