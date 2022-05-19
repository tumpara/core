import hashlib
from typing import Literal, Optional

import pyexiv2

from tumpara.libraries.models import Library

# This tuple contains the list of fields that are used to calculate a hash of EXIF data,
# which in turn is used to attribute photos to their raw counterparts, if any. The idea
# here is to use very generic fields that most photo editing / development tools most
# likely won't strip. Ultimately, these are more or less the same ones we read out on
# photos because they are the most popular. If an entry in this list has multiple keys,
# the first one that has a value is used. Further, if a tuple starts with ``True``, it
# is considered non-optional and no digest will be created if it is not present.
METADATA_DIGEST_FIELDS: list[
    str | tuple[str, str] | tuple[Literal[True], str, str, str]
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


def load_metadata(library: Library, path: str) -> pyexiv2.ImageMetadata:
    """Get metadata information of an image."""
    with library.storage.open(path, "rb") as file:
        metadata = pyexiv2.ImageMetadata.from_buffer(file.read())
        metadata.read()
    return metadata


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
