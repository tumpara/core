from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol

if TYPE_CHECKING:
    from PIL.Image import (
        Exif,
        Image,
        Palette,
        Resampling,
        Transform,
        Transpose,
        _Box,
        _Color,
        _ConversionMatrix,
        _Mode,
        _Resample,
        _Size,
        _Writeable,
    )
    from PIL.ImageFilter import Filter


class ImmutableImage(Protocol):
    """This protocol contains the immutable subset of Pillow's :class:`~PIL.Image.Image`
    API. Only fully typed methods are included here.
    """

    format: ClassVar[str | None]
    format_description: ClassVar[str | None]

    @property
    def width(self) -> int:
        ...

    @property
    def height(self) -> int:
        ...

    @property
    def size(self) -> tuple[int, int]:
        ...

    def tobytes(self, encoder_name: str = ..., *args: Any) -> bytes:
        ...

    def tobitmap(self, name: str = ...) -> bytes:
        ...

    def convert(
        self,
        mode: _Mode | None = ...,
        matrix: _ConversionMatrix | None = ...,
        dither: int | None = ...,
        palette: Palette | Literal[0, 1] = ...,
        colors: int = ...,
    ) -> Image:
        ...

    def quantize(
        self,
        colors: int = ...,
        method: Literal[0, 1, 2, 3] | None = ...,
        kmeans: int = ...,
        palette: Image | None = ...,
        dither: int = ...,
    ) -> Image:
        ...

    def copy(self) -> Image:
        ...

    def __copy__(self) -> Image:
        ...

    def crop(self, box: _Box | None = ...) -> Image:
        ...

    def filter(self, filter: Filter | Callable[[], Filter]) -> Image:
        ...

    def getbands(self) -> tuple[str, ...]:
        ...

    def getbbox(self) -> tuple[int, int, int, int] | None:
        ...

    def getcolors(self, maxcolors: int = ...) -> list[tuple[int, int]]:
        ...

    def getexif(self) -> Exif:
        ...

    def getpalette(self, rawmode: str | None = ...) -> list[int] | None:
        ...

    def histogram(
        self,
        mask: Image | None = ...,
        extrema: tuple[int, int] | tuple[float, float] | None = ...,
    ) -> list[int]:
        ...

    def entropy(
        self,
        mask: Image | None = ...,
        extrema: tuple[int, int] | tuple[float, float] | None = ...,
    ) -> float:
        ...

    def remap_palette(
        self, dest_map: Iterable[int], source_palette: Sequence[int] | None = ...
    ) -> Image:
        ...

    def resize(
        self,
        size: tuple[int, int],
        resample: Resampling | _Resample | None = ...,
        box: tuple[float, float, float, float] | None = ...,
        reducing_gap: float | None = ...,
    ) -> Image:
        ...

    def reduce(
        self, factor: int | tuple[int, int] | list[int], box: _Box | None = ...
    ) -> Image:
        ...

    def rotate(
        self,
        angle: float,
        resample: Resampling | _Resample = ...,
        expand: bool = ...,
        center: tuple[float, float] | None = ...,
        translate: tuple[float, float] | None = ...,
        fillcolor: _Color | None = ...,
    ) -> Image:
        ...

    def save(
        self,
        fp: str | bytes | Path | _Writeable,
        format: str | None = ...,
        *,
        save_all: bool = ...,
        bitmap_format: Literal["bmp", "png"] = ...,  # for ICO files
        optimize: bool = ...,
        **params: Any,
    ) -> None:
        ...

    def show(self, title: str | None = ...) -> None:
        ...

    def split(self) -> tuple[Image, ...]:
        ...

    def getchannel(self, channel: int | str) -> Image:
        ...

    def tell(self) -> int:
        ...

    def transform(
        self,
        size: _Size,
        method: Transform | Literal[0, 1, 2, 3, 4],
        data: Any = ...,
        resample: Resampling | _Resample = ...,
        fill: int = ...,
        fillcolor: _Color | int | None = ...,
    ) -> Image:
        ...

    def transpose(self, method: Transpose | Literal[0, 1, 2, 3, 4, 5, 6]) -> Image:
        ...

    def effect_spread(self, distance: int) -> Image:
        ...
