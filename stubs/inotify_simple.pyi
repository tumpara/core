import enum
import io
import os
from collections.abc import Generator
from typing import AnyStr, NamedTuple, Optional

__all__ = ["Event", "INotify", "flags", "masks", "parse_events"]

class Event(NamedTuple):
    wd: int
    mask: int
    cookie: int
    name: str

class INotify(io.FileIO):
    def __init__(self, inheritable: bool = False, nonblocking: bool = False): ...
    def add_watch(self, path: AnyStr | os.PathLike[AnyStr], mask: int) -> int: ...
    def rm_watch(self, wd: int) -> None: ...
    def read(  # type: ignore
        self, timeout: Optional[int] = None, read_delay: Optional[int] = None
    ) -> Generator[Event, None, None]: ...

def parse_events(data: bytes) -> list[Event]: ...

class flags(enum.IntEnum):
    ACCESS: int
    MODIFY: int
    ATTRIB: int
    CLOSE_WRITE: int
    CLOSE_NOWRITE: int
    OPEN: int
    MOVED_FROM: int
    MOVED_TO: int
    CREATE: int
    DELETE: int
    DELETE_SELF: int
    MOVE_SELF: int
    UNMOUNT: int
    Q_OVERFLOW: int
    IGNORED: int
    ONLYDIR: int
    DONT_FOLLOW: int
    EXCL_UNLINK: int
    MASK_ADD: int
    ISDIR: int
    ONESHOT: int
    @classmethod
    def from_mask(cls, mask: int) -> list[flags]: ...

class masks(enum.IntEnum):
    CLOSE: int
    MOVE: int
    ALL_EVENTS: int
