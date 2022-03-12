from collections.abc import Callable
from typing import Generator, Optional

import inotify_simple

__all__ = ["flags", "masks", "parse_events", "Event", "INotify"]

flags = inotify_simple.flags
masks = inotify_simple.masks
parse_events = inotify_simple.parse_events
Event = inotify_simple.Event

class INotify(inotify_simple.INotify):
    def __init__(self) -> None: ...
    def add_watch_recursive(
        self,
        path: str,
        mask: int,
        # The third argument here is unknown - in the upstream code, it is once
        # the literal True and once a flag. It is not documented.
        filter: Optional[Callable[[str, int, bool | int], bool]] = None,
    ) -> int: ...
    def rm_watch_recursive(self, wd: int) -> None: ...
    def get_path(self, wd: int) -> str: ...
    def read(  # type: ignore
        self, timeout: Optional[int] = None, read_delay: Optional[int] = None
    ) -> Generator[Event, None, None]: ...
