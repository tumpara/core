import ctypes
import functools
import multiprocessing
import multiprocessing.sharedctypes
import queue
from typing import cast

import pytest
from django.db import connection

from tumpara.libraries import scanner
from tumpara.libraries.models import File, Library
from tumpara.libraries.scanner import worker

from .models import GenericHandler
from .storage import TestingStorage
from .test_event_handling import library  # noqa: F401


@pytest.mark.django_db
def test_scanner_worker(monkeypatch: pytest.MonkeyPatch, library: Library) -> None:
    """The scanner worker successfully processes a series of events."""
    TestingStorage.set("foo", "content")
    TestingStorage.set("bar", "content")
    TestingStorage.set("baz", "content")

    event_queue: multiprocessing.JoinableQueue[
        scanner.Event
    ] = multiprocessing.JoinableQueue()
    event_queue.put(scanner.FileEvent("foo"))
    event_queue.put(scanner.FileEvent("bar"))
    event_queue.put(scanner.FileEvent("baz"))

    counter = multiprocessing.Value(ctypes.c_int, 0, lock=False)

    # Make sure the queue doesn't block so our test actually runs through.
    monkeypatch.setattr(
        event_queue, "get", functools.partial(event_queue.get, block=False)
    )
    # The worker process normally closes the connection after it's done (because it's
    # run in a standalone process). We don't want that because we need the database for
    # the assertions afterwards.
    monkeypatch.setattr(connection, "close", lambda: None)

    with pytest.raises(queue.Empty):
        worker.process(library.pk, event_queue, counter)

    assert counter.value == 3
    GenericHandler.objects.get(content=b"content")
    assert File.objects.count() == 3
