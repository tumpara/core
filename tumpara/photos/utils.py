import hashlib
import itertools
import math
import os.path
from typing import Literal, Optional, TypeVar

import blurhash
import dateutil.parser
import PIL.Image
import PIL.ImageOps
import pyexiv2
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from tumpara.libraries.models import Library

_T = TypeVar("_T")

# This tuple contains the list of fields that are used to calculate a hash of EXIF data,
# which in turn is used to attribute photos to their raw counterparts, if any. The idea
# here is to use very generic fields that most photo editing / development tools most
# likely won't strip. Ultimately, these are more or less the same ones we read out on
# photos because they are the most popular. If an entry in this list has multiple keys,
# the first one that has a value is used. Further, if a tuple starts with ``True``, it
# is considered non-optional and no digest will be created if it is not present.
METADATA_DIGEST_FIELDS: list[
    str
    | tuple[str]
    | tuple[str, str]
    | tuple[str, str, str]
    | tuple[Literal[True], str, str, str]
] = [
    (
        True,
        "Exif.Image.DateTimeOriginal",
        "Exif.Image.DateTime",
        "Exif.Image.DateTimeDigitized",
    ),
    "Exif.Image.Make",
    "Exif.Image.Model",
    "Exif.Photo.ISOSpeedRatings",
    "Exif.Photo.ExposureTime",
    ("Exif.Photo.FNumber", "Exif.Photo.ApertureValue"),
    "Exif.Photo.FocalLength",
]


def load_image(library: Library, path: str) -> PIL.Image.Image:
    """Open an image file with Pillow."""
    image = PIL.Image.open(library.storage.open(path, "rb"))
    return PIL.ImageOps.exif_transpose(image)


def load_metadata(library: Library, path: str) -> pyexiv2.ImageMetadata:
    """Get metadata information of an image."""
    with library.storage.open(path, "rb") as file:
        metadata = pyexiv2.ImageMetadata.from_buffer(file.read())
        metadata.read()
    return metadata


def extract_metadata_value(
    metadata: pyexiv2.ImageMetadata, cast: type[_T], *keys: str
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
                value = value.strip()
            return value  # type: ignore
        except:
            continue
    return None


def calculate_metadata_checksum(library: Library, path: str) -> Optional[bytes]:
    """Calculate a checksum out of all available image metadata.

    :return: Checksum that can be used to attribute two identical photos together. If
        this is ``None``, no checksum could be calculated.
    """
    metadata = load_metadata(library, path)

    hasher = hashlib.blake2b(digest_size=32)
    for keys in METADATA_DIGEST_FIELDS:
        # Parse the keys definition. It has one of the following forms:
        # - "Exif.Image.SomeKey"
        # - ("Exif.Image.SomeKey", "Exif.Image.SomeOtherKey", ...)
        # - (True, "Exif.Image.SomeKey")
        # - (True, "Exif.Image.SomeKey", "Exif.Image.SomeOtherKey", ...)
        # `True` in the first element means that this group is not optional.
        if isinstance(keys, str):
            keys = (keys,)
        if keys[0] is True:
            optional = False
            keys = keys[1:]
        else:
            optional = True

        found = False
        for key in keys:
            assert isinstance(key, str)
            value = metadata.get(key, None)
            if value is not None:
                found = True
                hasher.update(value.raw_value.encode())
                break

        if not optional and not found:
            return None

        # Use 0b1 as a kind of separator here.
        hasher.update(bytes(0b1))

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

    raw_image = list(
        itertools.chain.from_iterable(
            zip(
                thumbnail.getdata(band=0),
                thumbnail.getdata(band=1),
                thumbnail.getdata(band=2),
            )
        ),
    )
    return blurhash.encode(
        raw_image,
        # Limit the components so we stay inside the CharField's bounds.
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
