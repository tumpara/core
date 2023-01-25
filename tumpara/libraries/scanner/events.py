from __future__ import annotations

import abc
import dataclasses
import hashlib
import logging
import os.path
import re
from typing import TYPE_CHECKING, Optional, cast

from django.db import models, transaction
from django.utils import timezone

from ..signals import files_changed, new_file

if TYPE_CHECKING:
    from ..models import File, Library

_logger = logging.getLogger(__name__)


class Event(abc.ABC):
    """Base class for file events."""

    @abc.abstractmethod
    def commit(self, library: Library) -> None:
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
    def commit(self, library: Library) -> None:
        from ..models import Asset, File

        def bail(reason: str) -> None:
            """Bail out and mark all file objects for this path as unavailable."""
            _logger.debug(
                f"New file {self.path!r} in {library} - skipping because {reason}."
            )
            File.objects.filter(path=self.path, asset__library=library).update(
                availability=None
            )

        if library.check_path_ignored(self.path):
            bail("the file is in an ignored directory")
            return

        try:
            hasher = hashlib.blake2b(digest_size=32)
            with library.storage.open(self.path, "rb") as content:
                hasher.update(content.read())
            digest = hasher.hexdigest()
        except IOError:
            bail("the file could not be read")
            return

        # Fetch a list of existing assets that might match this file.
        file_candidates = list(
            File.objects.filter(
                models.Q(path=self.path) | models.Q(digest=digest),
                asset__library=library,
            )
        )
        candidates_by_path = {
            file for file in file_candidates if file.path == self.path
        }
        candidates_by_digest = {
            file for file in file_candidates if file.digest == digest
        }
        available_candidates = {file for file in file_candidates if file.available}
        unavailable_candidates = {
            file for file in file_candidates if not file.available
        }
        file: Optional[File] = None
        need_change_signal = False
        need_saving = False

        # First case: we have a file object that already matches the description we
        # have. This means that the file has not changed since the last time we scanned.
        if candidates := candidates_by_path & candidates_by_digest:
            file = candidates.pop()
            need_saving = True
            need_change_signal = True

            for other_file in candidates:
                if not other_file.available:
                    continue
                _logger.warning(
                    f"Got two matching file assets for the same path in a library, "
                    f"which should not happen. The file object {other_file} will be "
                    f"marked unavailable. This is probably a bug."
                )
                other_file.availability = None
                other_file.save()

        # Second case: we have some other unavailable file object on asset with the
        # same digest. Then that old file object can be replaced with this new one.
        elif candidates := candidates_by_digest & unavailable_candidates:
            file = candidates.pop()
            need_saving = True
            need_change_signal = True

        # Third case: we have existing database entries that match the digest, but are
        # currently available. Then we create a new file object in their asset (all
        # file objects with the same digest should always share a asset).
        elif candidates := candidates_by_digest & available_candidates:
            file = File(
                asset=candidates.pop().asset,
                path=self.path,
                digest=digest,
                availability=timezone.now(),
            )
            need_saving = True
            need_change_signal = True

        # Fourth case: we have an existing file object for this path that is marked
        # as available. This is the case when a file is edited on disk.
        elif candidates := candidates_by_path & available_candidates:
            file = candidates.pop()
            need_saving = True
            need_change_signal = True

        # Fifth case: we have an existing file object for this path that is marked as
        # unavailable. Note that this case might be problematic because there might now
        # be a file at that path that no longer matches the type of the one that was
        # there before.
        elif candidates := candidates_by_path & unavailable_candidates:
            file = candidates.pop()
            need_saving = True
            need_change_signal = True

        # Sixth case: we have a completely new file. Since we couldn't place the file
        # into any existing library asset, we can now create a new one. To do that,
        # we ask all the registered receivers of the `new_file` signal to see if we
        # find some content object that is willing to take the file (see the signal's
        # documentation for details).
        else:
            result = new_file.send_robust(
                context=library.context,
                path=self.path,
                library=library,
            )
            responses = [
                cast(Asset, response)
                for _, response in result
                if isinstance(response, Asset)
            ]
            if len(responses) == 0:
                bail("no compatible file handler was found")
                return
            elif len(responses) > 1:
                bail("more than one compatible file handler was found")
                return
            else:
                asset = responses[0]
                if asset._state.adding:
                    asset.save()

                file = File.objects.create(
                    asset=asset,
                    path=self.path,
                    digest=digest,
                    availability=timezone.now(),
                )
                need_change_signal = True

        # Mark all other files for that path that we might still have in the database
        # as unavailable (because we just created a new one).
        for other_file in candidates_by_path:
            if other_file == file:
                continue
            other_file.availability = None
            other_file.save(update_fields=("availability",))

        if need_saving:
            file.path = self.path
            file.digest = digest
            file.availability = timezone.now()
            file.save()

        if need_change_signal:
            resolved_asset = file.asset.resolve_instance()
            files_changed.send_robust(sender=type(resolved_asset), asset=resolved_asset)


@dataclasses.dataclass
class FileModifiedEvent(Event):
    """Event for files being modified.

    When this event is created for a file that is not yet on asset, it will be
    handled like a new file.
    """

    path: str

    @transaction.atomic
    def commit(self, library: Library) -> None:
        from ..models import File

        try:
            file = File.objects.get(
                asset__library=library,
                path=self.path,
                availability__isnull=False,
            )
        except File.DoesNotExist:
            _logger.debug(
                f"Got a file modified event for {self.path!r} in {library} which is "
                f"not on asset. Handling as a new file."
            )
            FileEvent(path=self.path).commit(library)
            return

        if library.check_path_ignored(self.path):
            file.availability = None
            file.save(update_fields=("availability",))
            _logger.debug(
                f"Got a file modified event for {self.path!r} in {library}, which is "
                f"in an ignored directory. The file was marked unavailable."
            )
            return

        if (
            file.availability is not None
            and file.availability > library.storage.get_modified_time(self.path)
            and file.availability > library.storage.get_created_time(self.path)
        ):
            # The file seems to still be available and hasn't changed since the last
            # time we checked, so go ahead and call it a day.
            file.availability = timezone.now()
            file.save(update_fields=("availability",))
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

    @transaction.atomic
    def commit(self, library: Library) -> None:
        from ..models import Asset, File

        file_queryset = File.objects.filter(
            asset__library=library, path=self.old_path, availability__isnull=False
        )
        touched_assets = list(Asset.objects.filter(file__in=file_queryset).distinct())

        if library.check_path_ignored(self.new_path):
            affected_rows = file_queryset.update(availability=None)
            _logger.debug(
                f"Moving file {self.old_path!r} to {self.new_path!r}, but the new path "
                f"is in an ignored directory. Assets were marked unavailable."
            )
            for asset in touched_assets:
                resolved_asset = asset.resolve_instance()
                files_changed.send_robust(
                    sender=type(resolved_asset), asset=resolved_asset
                )
        else:
            affected_rows = file_queryset.update(
                path=self.new_path, availability=timezone.now()
            )
            if affected_rows == 0:
                _logger.debug(
                    f"Got a file moved event for {self.old_path!r} to "
                    f"{self.new_path!r} in {library}, but no direct asset was "
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


@dataclasses.dataclass
class FileRemovedEvent(Event):
    """Event for a file being deleted or moved outside the library."""

    path: str

    def commit(self, library: Library) -> None:
        from ..models import Asset, File

        file_queryset = File.objects.filter(
            asset__library=library, path=self.path, availability__isnull=False
        )
        touched_assets = list(Asset.objects.filter(file__in=file_queryset).distinct())

        affected_rows = file_queryset.update(availability=None)
        if affected_rows == 0:
            _logger.debug(
                f"Got a file removed event for {self.path!r} in {library}, but no "
                f"asset was available."
            )
        else:
            if affected_rows > 1:
                _logger.warning(
                    "More than one file processed for file remove event which should "
                    "have been unique."
                )
            _logger.debug(f"Removed {self.path} in {library}.")

        for asset in touched_assets:
            resolved_asset = asset.resolve_instance()
            files_changed.send_robust(sender=type(resolved_asset), asset=resolved_asset)


@dataclasses.dataclass
class DirectoryMovedEvent(Event):
    """Event for a directory being renamed or moved while remaining inside the library."""

    old_path: str
    new_path: str

    @transaction.atomic
    def commit(self, library: Library) -> None:
        from ..models import Asset, File

        # The path.join stuff adds an additional slash at the end, making sure really
        # only files inside of the directory are targeted (not that other assets should
        # exist, but better safe than sorry). Also, we use regex here because SQLite
        # doesn't support case-sensitive startswith.
        # TODO: Check if we have a case-insensitive filesystem.
        path_regex = "^" + re.escape(os.path.join(self.old_path, ""))

        # We intentionally don't filter out unavailable files so they are moved along
        # with the other files in the directory. Yay, ghosts :)
        file_queryset = File.objects.filter(
            asset__library=library, path__regex=path_regex
        )
        touched_assets = list(Asset.objects.filter(file__in=file_queryset).distinct())

        if library.check_path_ignored(self.new_path):
            affected_rows = file_queryset.update(availability=None)
            _logger.debug(
                f"Moving directory {self.old_path!r} to {self.new_path!r}, but the new "
                f"path is in an ignored directory. {affected_rows} asset(s) were marked "
                f"unavailable."
            )

            for asset in touched_assets:
                resolved_asset = asset.resolve_instance()
                files_changed.send_robust(
                    sender=type(resolved_asset), asset=resolved_asset
                )
        else:
            count = 0
            for file in file_queryset:
                file.path = os.path.join(
                    self.new_path, os.path.relpath(file.path, self.old_path)
                )
                if file.availability is not None:
                    file.availability = timezone.now()
                file.save(update_fields=("path", "availability"))
                count += 1
            _logger.debug(
                f"Got a directory moved event from {self.old_path!r} to "
                f"{self.new_path!r} in {library} which affected {count} file(s)."
            )


@dataclasses.dataclass
class DirectoryRemovedEvent(Event):
    """Event for a directory being deleted or moved outside the library."""

    path: str

    @transaction.atomic
    def commit(self, library: Library) -> None:
        from ..models import Asset, File

        # As before, use regex instead of startswith because SQLite doesn't support the
        # latter case-sensitively.
        # TODO: Check if we have a case-insensitive filesystem.
        path_regex = "^" + re.escape(os.path.join(self.path, ""))

        file_queryset = File.objects.filter(
            asset__library=library, path__regex=path_regex, availability__isnull=False
        )
        touched_assets = list(Asset.objects.filter(file__in=file_queryset).distinct())

        affected_rows = file_queryset.update(availability=None)
        _logger.debug(
            f"Got a directory removed event for {self.path!r} in {library} which "
            f"affected {affected_rows} file(s)."
        )

        for asset in touched_assets:
            resolved_asset = asset.resolve_instance()
            files_changed.send_robust(sender=type(resolved_asset), asset=resolved_asset)


class ScanEvent(Event):
    """This event is sent after a full scan of the library.

    The event object should be created before beginning the scan and committed after all
    other events of the scan have been processed. It takes care of any leftover
    :class:`File` objects that are no longer available.

    .. warning::
        When using multiprocessing, this event should be treated as a critical section!
        Do not commit this when other threads are still processing events that are
        assumed to be done. Instead, wait for those to finish first.
    """

    def __init__(self) -> None:
        self.start_timestamp = timezone.now()

    @transaction.atomic
    def commit(self, library: Library) -> None:
        from ..models import Asset, File

        file_queryset = File.objects.filter(
            # Since all events mark their touched files as available with a new
            # timestamp, we can use that to find all the old assets that are no
            # longer available.
            availability__lte=self.start_timestamp,
            asset__library=library,
        )
        touched_assets = list(Asset.objects.filter(file__in=file_queryset).distinct())

        affected_rows = file_queryset.update(availability=None)
        _logger.debug(
            f"Marked {affected_rows} file objects in {library} as no longer available."
        )

        for asset in touched_assets:
            resolved_asset = asset.resolve_instance()
            files_changed.send_robust(sender=type(resolved_asset), asset=resolved_asset)
