import datetime
import functools
import hashlib
import io
import json
import math
import os.path
import subprocess
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Literal, Optional, TypeVar

import blurhash
import dateutil.parser
import exiv2
import numpy
import PIL.Image
import PIL.ImageFile
import PIL.ImageOps
import rawpy
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from tumpara.libraries.models import Library

_T = TypeVar("_T")


# Run configuration side effects.
PIL.ImageFile.LOAD_TRUNCATED_IMAGES = True
if settings.ENABLE_BMFF_METADATA:
    exiv2.enableBMFF()


# This list contains the fields that are used to calculate a hash of EXIF data,
# which in turn is used to attribute photos to their raw counterparts, if any. The
# idea here is to use very generic fields that most photo editing / development tools
# likely won't strip. But we also want to have enough fields to correctly identify
# images. Ultimately, these are more or less the same ones we read out on photos
# because they are the most popular. Note that there is an 'ImageUniqueID' field,
# but that isn't very popular and some editing tools might ignore it. So,
# it is deliberately ignored in this implementation.
METADATA_DIGEST_FIELDS: Sequence[str | Sequence[str]] = [
    "Exif.Image.Make",
    "Exif.Image.Model",
    "Exif.Photo.ISOSpeedRatings",
    "Exif.Photo.ExposureTime",
    ("Exif.Photo.FNumber", "Exif.Photo.ApertureValue"),
    "Exif.Photo.FocalLength",
]


def load_image(library: Library, path: str) -> tuple[PIL.Image.Image, bool]:
    """Open an image file with Pillow.

    :return: A tuple containing the Pillow :class:`~PIL.Image.Image` and a boolean that
        indicates whether the file was a raw image.
    """
    with library.storage.open(path, "rb") as file_io:
        try:
            raw_image = rawpy.imread(file_io)  # type: ignore
            try:
                # Case 1: we have a raw file with an embedded thumbnail. Use that
                # because it's probably already processed by the camera or photo
                # program, meaning it will look better than what we can render off of
                # the source.
                raw_thumb = raw_image.extract_thumb()
                if raw_thumb.format == rawpy.ThumbFormat.JPEG:
                    image = PIL.Image.open(io.BytesIO(raw_thumb.data))
                elif raw_thumb.format == rawpy.ThumbFormat.BITMAP:
                    image = PIL.Image.fromarray(raw_thumb.data)
                else:
                    raise rawpy.LibRawNoThumbnailError
                raw_original = True

            except rawpy.LibRawNoThumbnailError:
                # Case 2: we have a raw file, but it doesn't have a thumbnail. Here, we
                # need to process the image ourselves.
                image = PIL.Image.fromarray(raw_image.postprocess())
                raw_original = True

        except rawpy.LibRawFileUnsupportedError:
            # Case 3: the image is not a raw file. Hopefully, Pillow can deal with it.
            file_io.seek(0)
            image = PIL.Image.open(file_io)
            raw_original = False

        image = PIL.ImageOps.exif_transpose(image)
    return image, raw_original


class Exiv2ImageMetadata:
    """Metadata container that holds EXIF (and other) metadata of an image."""

    def __init__(self, library: Library, path: str) -> None:
        """Open the image at the specified path in a library."""
        with library.storage.open(path, "rb") as file:
            image_data = file.read()
            exiv2_image = exiv2.ImageFactory.open(image_data)
            exiv2_image.readMetadata()
            self._exif_data = exiv2_image.exifData()
            self._iptc_data = exiv2_image.iptcData()
            self._xmp_data = exiv2_image.xmpData()

    @staticmethod
    def _get_int_datum_value(self, datum: Optional[exiv2.Exifdatum]) -> Optional[int]:
        if datum is None:
            return None
        assert isinstance(datum, exiv2.Exifdatum)
        assert len(value_container := list(datum.getValue())) == 1
        assert isinstance(result := value_container[0], int)
        return result

    @property
    def iso_speed(self) -> Optional[int]:
        return self._get_int_datum_value(exiv2.isoSpeed(self._exif_data))

    # TODO DateTimeOriginal

    @property
    def flash_bias(self) -> Optional[int]:
        return self._get_int_datum_value(exiv2.flashBias(self._exif_data))

    @property
    def exposure_mode(self) -> Optional[int]:
        return self._get_int_datum_value(exiv2.exposureMode(self._exif_data))

    @property
    def scene_mode(self) -> Optional[int]:
        return self._get_int_datum_value(exiv2.sceneMode(self._exif_data))

    @property
    def macro_mode(self) -> Optional[int]:
        return self._get_int_datum_value(exiv2.macroMode(self._exif_data))


def load_metadata(library: Library, path: str) -> "pyexiv2.ImageMetadata":
    """Get metadata information of an image."""
    with library.storage.open(path, "rb") as file:
        metadata = pyexiv2.ImageMetadata.from_buffer(file.read())
        metadata.read()
    return metadata


def extract_metadata_value(
    metadata: "pyexiv2.ImageMetadata", cast: type[_T], *keys: str
) -> Optional[_T]:
    """Extract a single entry of metadata information for an image.

    :param metadata: The metadata object from :func:`load_metadata`.
    :param cast: Values will be cast to this type.
    :param keys: Names of the keys to try, in order. The first key that is present with
        a valid value will be used.
    """
    for key in keys:
        try:
            value = metadata[key].value
            value = cast(value)  # type: ignore
            if isinstance(value, str):
                value = unicodedata.normalize("NFC", value.strip())
            return value  # type: ignore
        except:
            continue
    return None


def extract_timestamp(
    metadata: "pyexiv2.ImageMetadata",
    variant: Literal["", "Digitized", "Original"],
) -> Optional[timezone.datetime]:
    """Extract one of the three metadata timestamps from an image metadata object.

    :param metadata: The metadata object from :func:`load_metadata`.
    :param variant: One of ``""``, ``"Digitized"`` or ``"Original"``, depending on the
        timestamp you want.
    """
    base_result = extract_metadata_value(
        metadata,
        timezone.datetime,
        f"Exif.Image.DateTime{variant}",
        f"Exif.Photo.DateTime{variant}",
    )
    if base_result is None:
        return None

    raw_subsec_value = (
        extract_metadata_value(
            metadata,
            str,
            f"Exif.Image.SubSecTime{variant}",
            f"Exif.Photo.SubSecTime{variant}",
        )
        or ""
    )
    # Some cameras only use a 10ms precision here. In order to keep compatibility with
    # editing tools that parse this and make a correct millisecond counter out of it,
    # we might need to add a few zeros. But, if we get a subsec counter with more than
    # three digits, we need to be able to parse that as well. So, this formula correctly
    # sets the decimal point:
    raw_subsec_value += "000"
    milliseconds = float(raw_subsec_value) / (10 ** (len(raw_subsec_value) - 3))

    return base_result + datetime.timedelta(milliseconds=milliseconds)


def calculate_metadata_checksum(library: Library, path: str) -> Optional[bytes]:
    """Calculate a checksum out of all available image metadata.

    :return: Checksum that can be used to attribute two identical photos together. If
        this is ``None``, no checksum could be calculated.
    """
    metadata = load_metadata(library, path)

    hasher = hashlib.blake2b(digest_size=32)

    try:
        hasher.update(extract_timestamp(metadata, "Original").isoformat().encode())
    except KeyError:
        # The timestamp is an integral part.
        return None

    for metadata_key_name_or_names in METADATA_DIGEST_FIELDS:
        metadata_keys = (
            metadata_key_name_or_names
            if isinstance(metadata_key_name_or_names, Sequence)
            else [metadata_key_name_or_names]
        )

        for metadata_key in metadata_keys:
            assert isinstance(metadata_key, str)
            value = metadata.get(metadata_key, None)
            if value is not None:
                hasher.update(bytes(0b1))
                hasher.update(value.raw_value.encode())
                break
        else:
            hasher.update(bytes(0b0))

    return hasher.digest()


def calculate_blurhash(image: PIL.Image.Image) -> str:
    if settings.BLURHASH_SIZE < 1 or settings.BLURHASH_SIZE is None:
        raise ImproperlyConfigured("blurhash calculation has been disabled")

    # For the blurhash, make sure that the following is approximately true:
    # - BLURHASH_SIZE = a * b
    # - a / b = width / height
    # This distributes the requested size of the blurhash among the two axis
    # appropriately.
    b = math.sqrt(settings.BLURHASH_SIZE / image.width * image.height)
    a = b * image.width / image.height
    thumbnail = image.convert("RGB")
    thumbnail.thumbnail(
        (settings.BLURHASH_SIZE * 10, settings.BLURHASH_SIZE * 10),
        PIL.Image.BICUBIC,
    )

    return blurhash.encode(
        numpy.array(thumbnail),
        # Limit the components, so we stay inside the CharField's bounds.
        components_x=max(0, min(math.ceil(a), 8)),
        components_y=max(0, min(math.ceil(b), 8)),
    )


def extract_timestamp_from_filename(path: str) -> Optional[timezone.datetime]:
    """Try to extract a timestamp from a filename."""
    try:
        basename = os.path.basename(path)
        return dateutil.parser.parse(basename, fuzzy=True, ignoretz=True)
    except ValueError:
        return None
