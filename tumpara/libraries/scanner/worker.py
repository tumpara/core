from __future__ import annotations

import ctypes
import logging
import multiprocessing.sharedctypes
import time
from typing import Any, cast

import django
from django.conf import settings
from django.db import connection, transaction

from tumpara.utils import exiftool

from . import Event

__all__ = ["worker"]
_logger = logging.getLogger(__name__)


def process(
    library_pk: int,
    queue: multiprocessing.JoinableQueue[Event],
    _counter: multiprocessing.sharedctypes.SynchronizedBase[ctypes.c_int],
    _group_start_time: multiprocessing.sharedctypes.SynchronizedBase[ctypes.c_double],
) -> None:
    """Worker process for multiprocessed event handling.

    :param library_pk: ID of the library that is currently being scanned.
    :param queue: Queue to receive scanner events.
    :param counter: Counter value used to report back how many events have been handled.
    """

    # Call django.setup here because this worker is run in a standalone process. The
    # imports are delayed until here because they require the setup call beforehand.
    django.setup()
    from ..models import Library

    library = Library.objects.get(pk=library_pk)

    try:
        while True:
            event: Event = queue.get()

            with transaction.atomic():
                try:
                    event.commit(library)
                except:  # noqa
                    try:
                        event_path = cast(Any, event).path
                    except AttributeError:
                        try:
                            event_path = cast(Any, event).new_path
                        except AttributeError:
                            event_path = None

                    _logger.exception(
                        f"Error while handling event of type {type(event)}"
                        + (
                            f" for path {event_path!r}"
                            if event_path is not None
                            else ""
                        )
                        + "."
                    )

            with _counter.get_lock():
                counter = cast(ctypes.c_int, _counter)
                counter.value += 1
                if counter.value % settings.REPORT_INTERVAL == 0 and counter.value > 0:
                    group_start_time = cast(ctypes.c_double, _group_start_time)
                    process_rate = round(
                        settings.REPORT_INTERVAL
                        / (time.time() - group_start_time.value)
                    )
                    _logger.info(
                        f"{counter.value} events processed so far (about {process_rate} "
                        f"per second)."
                    )
                    group_start_time.value = time.time()

            queue.task_done()
    finally:
        connection.close()
        exiftool.stop_exiftool()
