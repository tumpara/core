from collections.abc import Sequence
from typing import BinaryIO

class LibRawError(Exception):
    pass

class LibRawNonFatalError(LibRawError):
    pass

class LibRawFileUnsupportedError(LibRawNonFatalError):
    pass

class RawPy:
    def postprocess(self) -> Sequence[Sequence[tuple[int, int, int]]]: ...

def imread(pathOrFile: str | BinaryIO) -> RawPy: ...
