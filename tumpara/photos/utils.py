import datetime
import functools
import hashlib
import io
import json
import logging
import math
import os.path
import re
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Optional, TypeVar, overload

import blurhash
import dateutil.parser
import numpy
import PIL.Image
import PIL.ImageFile
import PIL.ImageOps
import rawpy
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from tumpara.libraries.models import Library

_logger = logging.getLogger(__name__)

_T = TypeVar("_T")
_Number = TypeVar("_Number", bound="int | float")


# Run configuration side effects.
PIL.ImageFile.LOAD_TRUNCATED_IMAGES = True


remove_whitespace = functools.partial(
    re.compile(r"\s").sub,
    "",
)


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


class ImageMetadata:
    """Metadata container that holds EXIF (and other) metadata of an image."""

    def __init__(self) -> None:
        self._metadata = dict[str, Any]()
        self._formatted_metadata = dict[str, Any]()

    @staticmethod
    def load(library: Library, path: str) -> "ImageMetadata":
        """Open the image at the specified path in a library.

        This will gracefully fall back to an empty metadata container if no information
        is found. Also note that Exiftool supports file types other than images (like
        plain text files), so getting a result here does not yet imply that the file is
        a functioning image!

        The reason we use Exiftool with subprocesses and not a library like exiv2 (which
        we would call directly and therefore improving performance) is because Exiftool
        does a lot of normalization between different Camera vendors. For example, the
        different exposure programs that are not always located in the default
        Exif.Photo.ExposureProgram field (some information is in the maker note) are all
        bundled together in a single "ExposureProgram" field when parsing with Exiftool.
        """
        try:
            with library.storage.open(path, "rb") as file_io:
                raw_exiftool_result = subprocess.check_output(
                    [
                        settings.EXIFTOOL_BINARY,
                        "-",
                        "-json",
                        "-n",
                    ],
                    stdin=file_io,
                    stderr=subprocess.DEVNULL,
                )
                exiftool_result = json.loads(raw_exiftool_result)
                assert isinstance(exiftool_result, Sequence)
                assert len(exiftool_result) == 1
                assert isinstance(exiftool_result[0], Mapping)

                file_io.seek(0)

                raw_formatted_exiftool_result = subprocess.check_output(
                    [
                        settings.EXIFTOOL_BINARY,
                        "-",
                        "-json",
                        "-d",
                        "%Y-%m-%dT%H:%M:%S%6f",
                    ],
                    stdin=file_io,
                    stderr=subprocess.DEVNULL,
                )
                formatted_exiftool_result = json.loads(raw_formatted_exiftool_result)
                assert isinstance(formatted_exiftool_result, Sequence)
                assert len(formatted_exiftool_result) == 1
                assert isinstance(formatted_exiftool_result[0], Mapping)

            image_metadata = ImageMetadata()
            image_metadata._metadata = exiftool_result[0]  # type: ignore[assignment]
            image_metadata._formatted_metadata = formatted_exiftool_result[0]  # type: ignore[assignment]
            return image_metadata
        except FileNotFoundError:
            if not os.path.exists(settings.EXIFTOOL_BINARY):
                _logger.warning(
                    f"Could not find the specified Exiftool binary "
                    f"{settings.EXIFTOOL_BINARY!r}. Image metadata cannot be read."
                )
                return ImageMetadata()
            else:
                raise
        except subprocess.CalledProcessError:
            return ImageMetadata()

    def _get_numeric_value(
        self,
        key: str,
        allow_negative: bool = False,
        allow_zero: bool = False,
        require_finite: bool = True,
    ) -> Optional[float]:
        raw_value = self._metadata.get(key)
        if raw_value is None:
            return None
        try:
            value = float(raw_value)
            assert allow_negative is True or value >= 0
            assert allow_zero is True or value != 0
            assert require_finite is False or math.isfinite(value)
            return value
        except (AssertionError, TypeError, ValueError):
            # TODO Raise a warning.
            return None

    def _get_integer_value(
        self, key: str, allow_negative: bool = False, allow_zero: bool = False
    ) -> Optional[int]:
        value = self._get_numeric_value(
            key, allow_negative, allow_zero, require_finite=True
        )
        if value is None:
            return None
        return round(value)

    def _get_string_value(self, key: str) -> str:
        value = self._formatted_metadata.get(key)
        if value is None:
            return ""
        elif isinstance(value, (str, float, int)):
            return str(value)
        else:
            # TODO Raise a warning.
            return ""

    @functools.cached_property
    def timestamp(self) -> Optional[datetime.datetime]:
        value = ""
        for key in (
            "SubSecDateTimeOriginal",
            "SubSecCreateDate",
            "DateTimeOriginal",
            "CreateDate",
        ):
            try:
                value = self._formatted_metadata[key]
            except KeyError:
                continue
            else:
                if value:
                    break

        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.datetime.fromisoformat(value)
        except ValueError:
            return None

    aperture_size = functools.cached_property(
        functools.partial(_get_numeric_value, key="Aperture")
    )
    camera_make = functools.cached_property(
        functools.partial(_get_string_value, key="Make")
    )
    exposure_program_description = functools.cached_property(
        functools.partial(_get_string_value, key="ExposureProgram")
    )
    exposure_time = functools.cached_property(
        functools.partial(_get_numeric_value, key="ExposureTime")
    )
    flash_description = functools.cached_property(
        functools.partial(_get_string_value, key="Flash")
    )
    focal_length = functools.cached_property(
        functools.partial(_get_numeric_value, key="FocalLength")
    )
    focus_mode_description = functools.cached_property(
        functools.partial(_get_string_value, key="FocusMode")
    )
    iso_value = functools.cached_property(
        functools.partial(_get_integer_value, key="ISO")
    )
    lens_identifier = functools.cached_property(
        functools.partial(_get_string_value, key="LensID")
    )
    macro_mode_description = functools.cached_property(
        functools.partial(_get_string_value, key="MacroMode")
    )
    metering_mode_description = functools.cached_property(
        functools.partial(_get_string_value, key="MeteringMode")
    )
    software = functools.cached_property(
        functools.partial(_get_string_value, key="Software")
    )

    @functools.cached_property
    def camera_model(self) -> str:
        value = self._get_string_value("Model")
        if not value or not self.camera_make:
            return ""

        # Some camera vendors put their name in the model field as well, which is a bit
        # redundant. We would like to be able to concatenate the make and model fields
        # and get a string that nicely describes the camera, so we remove any redundancy
        # here. Otherwise, we might get things like this when putting the make and model
        # together:
        # - "NIKON CORPORATION NIKON D90"
        # - "Canon Canon EOS 5D Mark III"
        # By removing the common prefix from the model field, the two examples above
        # become "NIKON CORPORATION D90" and "Canon EOS 5D Mark III" when put together.
        camera_prefix = os.path.commonprefix([self.camera_make.lower(), value.lower()])
        if (
            # Fix things like "FUJIFILM FinePix A202" becoming "FUJIFILM inePix A202".
            len(camera_prefix) < len(self.camera_make)
            and not camera_prefix.endswith(" ")
        ):
            camera_prefix = ""
        if camera_prefix:
            return value[len(camera_prefix) :].strip()
        else:
            return value

    def calculate_checksum(
        self,
        *,
        payload: Optional[bytes | int] = None,
        use_file_identifier: bool = False,
    ) -> Optional[bytes]:
        """Calculate a checksum out of image metadata that can be used to attribute to
        identical photos together.

        The idea behind this value is that it does not change when a photo has been
        edited by some software. This allows us to figure out when an image is developed
        from a raw file, for example.

        :param payload: Optional payload that will be encoded into the hash as well.
        :param use_file_identifier: Whether to incorporate the serial number and file
            number fields into the checksum. Not all image processing tools keep these
            fields, however. Therefore, this is disabled by default.
        """
        file_identifier = ""
        if use_file_identifier:
            serial_number = remove_whitespace(
                self._get_string_value("SerialNumber")
                + self._get_string_value("InternalSerialNumber")
            )
            file_number = remove_whitespace(
                self._get_string_value("FileNumber")
                + self._get_string_value("FileIndex")
            )
            if serial_number and file_number:
                file_identifier = " ".join(
                    (
                        serial_number,
                        self._get_string_value("SerialNumberFormat"),
                        file_number,
                    )
                )

        if not self.timestamp and not file_identifier:
            # We have no sufficiently unique identification, so we can't build a
            # checksum.
            return None

        hasher = hashlib.blake2b(digest_size=32)

        if payload is not None:
            hasher.update(bytes(0b1))
            hasher.update(bytes(payload))
        else:
            hasher.update(bytes(0b0))

        if self.timestamp:
            hasher.update(bytes(0b1))
            hasher.update(self.timestamp.isoformat().encode())
        else:
            hasher.update(bytes(0b0))

        if file_identifier:
            hasher.update(bytes(0b1))
            hasher.update(file_identifier.encode())
        else:
            hasher.update(bytes(0b0))

        hasher.update(self.camera_make.encode())
        hasher.update(self.camera_model.encode())

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
