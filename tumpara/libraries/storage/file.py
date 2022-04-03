import logging
import os
import urllib.parse
from collections import deque
from typing import Literal

import inotify_simple
import inotifyrecursive
from django.core.exceptions import ValidationError
from django.core.files import storage as django_storage
from inotifyrecursive import flags as inotify_flags

from .. import scanner
from .base import LibraryStorage, WatchGenerator

__all__ = ["FileSystemBackend"]
_logger = logging.getLogger(__name__)


class FileSystemBackend(LibraryStorage, django_storage.FileSystemStorage):
    # pylint: disable-next=super-init-not-called
    def __init__(self, parsed_uri: urllib.parse.ParseResult):
        django_storage.FileSystemStorage.__init__(self, parsed_uri.path)

    def check(self) -> None:
        if not os.path.exists(self.base_location):
            raise ValidationError(
                f"The specified path {self.base_location} does not exist."
            )
        if not os.path.isdir(self.base_location):
            raise ValidationError(
                f"The specified path {self.base_location} is not a directory."
            )

    def watch(self) -> WatchGenerator:
        inotify = inotifyrecursive.INotify()
        watch = inotify.add_watch_recursive(
            self.base_location,
            inotify_flags.CREATE
            | inotify_flags.DELETE
            | inotify_flags.MODIFY
            | inotify_flags.MOVED_FROM
            | inotify_flags.MOVED_TO,
        )
        # TODO Inotify provides another flag DELETE_SELF that should be handled somehow.

        def decode_event(
            event: inotifyrecursive.Event,
        ) -> tuple[str, list[inotify_flags], str]:
            """Decode an inotify event into the corresponding path (relative to the
            library root) and flags.
            """
            absolute_path = os.path.join(inotify.get_path(event.wd), event.name)
            path = os.path.relpath(absolute_path, self.base_location)
            flags = inotify_flags.from_mask(event.mask)
            return path, flags, absolute_path

        # Send an always-None response, so we can start the generator manually in the
        # tests (the generator's initialization code isn't run otherwise). This
        # shouldn't have any drawbacks in actual usage.
        response: None | int | Literal[False, "check_empty"] = yield None

        while response is not False:
            # This generator may take a special value that is only used in tests
            # as input from send(). It checks if the inotify backend has any more
            # events. If it does not, it yields True to indicate so.
            if response == "check_empty":  # pragma: no cover
                # Use the inotify_simple API here because inotifyrecursive
                # doesn't proxy the timeout parameter.
                debug_events = [
                    event
                    for event in inotify_simple.INotify.read(inotify, timeout=0)
                    if event.mask & inotify_flags.IGNORED == 0
                ]
                if len(debug_events) == 0:
                    response = yield True  # type: ignore
                else:
                    response = yield debug_events  # type: ignore

                continue

            # Take a timeout value from the input. This is also used inside tests.
            events = deque(
                inotify.read(timeout=response if isinstance(response, int) else None)
            )

            if len(events) == 0:
                response = yield None

            while response is not False and len(events) > 0:
                event = events.popleft()
                path, flags, absolute_path = decode_event(event)
                if len(events) > 0:
                    next_event = events[0]
                    next_path, next_flags, next_absolute_path = decode_event(next_event)
                else:
                    next_path, next_flags, next_absolute_path = None, [], None

                if inotify_flags.MOVED_FROM in flags:
                    # For MOVED_FROM events, check if the next event is a corresponding
                    # MOVED_TO event. If so, then a file or directory was moved inside
                    # the library.
                    if inotify_flags.MOVED_TO in next_flags:
                        assert isinstance(next_path, str)
                        assert isinstance(next_absolute_path, str)

                        if (
                            inotify_flags.ISDIR in flags
                            and inotify_flags.ISDIR in next_flags
                        ):
                            # A directory was moved inside of the library.
                            events.popleft()
                            response = yield scanner.DirectoryMovedEvent(
                                old_path=path, new_path=next_path
                            )
                            continue
                        elif (
                            inotify_flags.ISDIR not in flags
                            and inotify_flags.ISDIR not in next_flags
                            and os.path.isfile(next_absolute_path)
                        ):
                            # A file was moved inside of the library.
                            events.popleft()
                            response = yield scanner.FileMovedEvent(
                                old_path=path, new_path=next_path
                            )
                            continue
                        else:
                            # The next event had nothing to do with the current one.
                            # This state should not actually happen.
                            # TODO: Raise a warning here.
                            _logger.warning(
                                "Received a pair of inotify events that shouldn't go "
                                "together (%s and %s). This is probably a bug.",
                                flags,
                                next_flags,
                            )

                    # A file or directory was moved out of the library.
                    if inotify_flags.ISDIR in flags:
                        response = yield scanner.DirectoryRemovedEvent(path=path)
                    else:
                        response = yield scanner.FileRemovedEvent(path=path)
                elif inotify_flags.MOVED_TO in flags:
                    if inotify_flags.ISDIR in flags:
                        for filename in self.walk_files(path):
                            response = yield scanner.FileEvent(path=filename)
                            if response is False:  # pragma: no cover
                                break
                    elif os.path.isfile(absolute_path):
                        response = yield scanner.FileEvent(path=path)
                elif inotify_flags.CREATE in flags:
                    if inotify_flags.ISDIR not in flags and os.path.isfile(
                        absolute_path
                    ):
                        # When creating and directly saving a file, two inotify events
                        # may be received - a CREATE and a MODIFY event. If this is the
                        # case, the latter event is scrapped so the client only receives
                        # a FileEvent doesn't get an additional FileModifiedEvent
                        # following it.
                        if (
                            inotify_flags.ISDIR not in next_flags
                            and inotify_flags.MODIFY in next_flags
                            and next_path == path
                        ):
                            events.popleft()
                        response = yield scanner.FileEvent(path=path)
                elif inotify_flags.MODIFY in flags:
                    if inotify_flags.ISDIR not in flags and os.path.isfile(
                        absolute_path
                    ):
                        response = yield scanner.FileModifiedEvent(path=path)
                elif inotify_flags.DELETE in flags:
                    if inotify_flags.ISDIR not in flags:
                        response = yield scanner.FileRemovedEvent(path=path)
                else:  # pragma: no cover
                    _logger.warning(
                        f"Received an inotify event that could not be handled (path "
                        f"{path}, mask {event.mask}). This is probably a bug."
                    )

        try:
            inotify.rm_watch_recursive(watch)
        except OSError:
            pass
