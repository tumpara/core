import enum
from collections.abc import Sequence
from typing import BinaryIO

class LibRawError(Exception):
    pass

class LibRawNonFatalError(LibRawError):
    pass

class LibRawNoThumbnailError(LibRawNonFatalError):
    pass

class LibRawFileUnsupportedError(LibRawNonFatalError):
    pass

class ThumbFormat(enum.Enum):
    JPEG = ...
    BITMAP = ...

class Thumbnail:
    format: ThumbFormat
    data: bytes

class RawPy:
    def postprocess(self) -> Sequence[Sequence[tuple[int, int, int]]]: ...
    def extract_thumb(self) -> Thumbnail: ...

def imread(pathOrFile: str | BinaryIO) -> RawPy: ...
