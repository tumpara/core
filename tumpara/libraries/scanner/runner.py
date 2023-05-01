from __future__ import annotations

import ctypes
import logging
import multiprocessing
import os
import time
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.db import connection, transaction

from tumpara.utils import exiftool

from .. import storage

if TYPE_CHECKING:
    from ..models import Library

__all__ = ["run"]
_logger = logging.getLogger(__name__)


# This is used by tests to bypass the exception handling while running sequentially.
RAISE_EXCEPTIONS = False


def check_thread_count(requested_thread_count: Optional[int] = None) -> int:
    if requested_thread_count is None:
        requested_thread_count = max(1, int((os.cpu_count() or 1) * 0.9))
    elif not isinstance(requested_thread_count, int):
        raise TypeError("requested thread count must be an integer")
    elif requested_thread_count < 1:
        raise ValueError("requested thread count must be at least 1")

    if (
        connection.settings_dict["ENGINE"]
        in ["django.db.backends.sqlite3", "django.contrib.gis.db.backends.spatialite"]
        and requested_thread_count != 1
    ):
        _logger.info(
            f"Ignoring requested thread count of {requested_thread_count} to avoid "
            f"concurrency issues with the SQLite backend."
        )
        return 1

    try:
        import dlib  # type: ignore

        if dlib.DLIB_USE_CUDA and requested_thread_count != 1:
            _logger.info(
                f"Ignoring requested thread count of {requested_thread_count} "
                f"because CUDA is active."
            )
            return 1
    except ImportError:
        pass

    return requested_thread_count


def run_sequential(library: Library, events: storage.WatchGenerator) -> None:
    """Handle scanner events for a library sequentially.

    :see: :func:`run`
    """
    _logger.info(f"Sequentially handling scanner events for library {library}.")

    group_start_time = time.perf_counter()

    for index, event in enumerate(events):
        if event is None:
            continue

        with transaction.atomic():
            try:
                event.commit(library)
            except:  # noqa
                if RAISE_EXCEPTIONS:
                    raise
                _logger.exception(f"Error while handling event of type {type(event)}.")

        if (
            index % settings.REPORT_INTERVAL == settings.REPORT_INTERVAL - 1
        ):  # pragma: no cover
            process_rate = round(
                settings.REPORT_INTERVAL / (time.perf_counter() - group_start_time)
            )
            _logger.info(
                f"{index + 1} events processed so far (about {process_rate} per "
                f"second)."
            )
            group_start_time = time.perf_counter()

    exiftool.stop_exiftool()


def run_parallel(
    library: Library, events: storage.WatchGenerator, thread_count: int
) -> None:
    """Handle scanner events for a library in parallel.

    :see: :func:`run`
    """
    assert thread_count > 1, "use run_sequential for single-threaded scanning"

    _logger.info(
        f"Handling scanner events for library {library} with {thread_count} workers."
    )

    # Spawn the requested number of worker processes and initialize the queue.
    context = multiprocessing.get_context("spawn")
    queue = context.JoinableQueue(maxsize=2 * thread_count)
    counter = context.Value(ctypes.c_int, 0, lock=True)
    group_start_time = context.Value(ctypes.c_double, time.time())

    # Close the active database connection as this can cause issues with
    # multiprocessing. See here for details: https://stackoverflow.com/a/10684672
    connection.close()

    from .worker import process

    workers = []
    for index in range(thread_count):
        worker = context.Process(
            target=process,
            args=(library.id, queue, counter, group_start_time),
            daemon=True,
        )
        workers.append(worker)
        worker.start()

    while True:
        try:
            event = next(events)
            if event is None:
                continue
            queue.put(event)
        except StopIteration:
            break

    _logger.debug("Received last event. Waiting for handlers to finish...")
    queue.join()
    _logger.info(f"Finished event handling for {library}.")


def run(
    library: Library,
    events: storage.WatchGenerator,
    *,
    thread_count: Optional[int] = None,
) -> None:
    """Handle scanner events for a library, automatically determining

    :param library: The library that is currently being scanned.
    :param events: Generator that provides scanner events.
    :param thread_count: Number of processes to launch. Setting this to `None` will
        use 90% of available CPUs. This parameter may be ignored under certain
        circumstances to avoid concurrency issues (currently these cases are when using
        SQLite or CUDA). Setting this to 1 disables concurrency completely.
    :param kwargs: Additional flags that will be passed on to event handlers.
    """
    thread_count = check_thread_count(thread_count)

    if thread_count == 1:
        run_sequential(library, events)
    else:
        run_parallel(library, events, thread_count)
