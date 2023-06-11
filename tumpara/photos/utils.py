import datetime
import functools
import hashlib
import io
import logging
import math
import os.path
import re
import subprocess
from collections.abc import Sequence
from typing import Any, ClassVar, Literal, Optional, TypeVar, Union, cast, overload

import blurhash
import dateutil.parser
import PIL.Image
import PIL.ImageFile
import PIL.ImageOps
import rawpy
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files import storage as django_storage

from tumpara.libraries.models import Library
from tumpara.utils import exiftool

from .types import ImmutableImage

_logger = logging.getLogger(__name__)

_T = TypeVar("_T")
_Number = TypeVar("_Number", bound="int | float")


# Run configuration side effects.
PIL.ImageFile.LOAD_TRUNCATED_IMAGES = True

AVIF_SUPPORTED: bool
try:
    import pillow_avif.AvifImagePlugin  # type: ignore[import]

    AVIF_SUPPORTED = pillow_avif.AvifImagePlugin.SUPPORTED
except ImportError:
    AVIF_SUPPORTED = False


remove_whitespace = functools.partial(
    re.compile(r"\s").sub,
    "",
)


def load_image(
    library: Library, path: str, *, maybe_raw: bool = True
) -> tuple[PIL.Image.Image, bool]:
    """Open an image file with Pillow.

    :param library: The library containing the image to load.
    :param path: Path of the image file inside the library.
    :param maybe_raw: Set this to :obj:`False` if you know the image won't be a raw
        image. In that case, decoding with rawpy is skipped.
    :return: A tuple containing the Pillow :class:`~PIL.Image.Image` and a boolean that
        indicates whether the file was a raw image.
    """
    with library.storage.open(path, "rb") as file_io:
        try:
            if not maybe_raw:
                raise rawpy.LibRawFileUnsupportedError

            raw_image = rawpy.imread(file_io)  # type: ignore
            try:
                # Case 1: we have a raw file with an embedded thumbnail. Use that
                # because it's probably already processed by the camera or photo
                # program, meaning it will look better than what we can render off of
                # the source.
                raw_thumb = raw_image.extract_thumb()
                if raw_thumb.format == rawpy.ThumbFormat.JPEG:
                    image = PIL.Image.open(io.BytesIO(raw_thumb.data))
                    _logger.debug(
                        f"Loaded JPEG thumbnail from raw image {path!r} from {library}"
                    )
                elif raw_thumb.format == rawpy.ThumbFormat.BITMAP:
                    image = PIL.Image.fromarray(raw_thumb.data)
                    _logger.debug(
                        f"Loaded bitmap thumbnail from raw image {path!r} from "
                        f"{library}"
                    )
                else:
                    raise rawpy.LibRawNoThumbnailError
                raw_original = True

            except rawpy.LibRawNoThumbnailError:
                # Case 2: we have a raw file, but it doesn't have a thumbnail. Here, we
                # need to process the image ourselves.
                image = PIL.Image.fromarray(raw_image.postprocess())
                _logger.debug(f"Developed raw image {path!r} from {library}")
                raw_original = True

        except rawpy.LibRawFileUnsupportedError:
            # Case 3: the image is not a raw file. Hopefully, Pillow can deal with it.
            file_io.seek(0)
            image = PIL.Image.open(file_io)
            image.load()
            _logger.debug(f"Opened regular image {path!r} from {library}")
            raw_original = False

        # exif_transpose() will return a copy if the image doesn't need rotation. In
        # this case, the original image will do. This improves performance quite a bit,
        # especially for large images.
        original_copy = image.copy
        image.copy = lambda: image  # type: ignore[assignment]
        image = PIL.ImageOps.exif_transpose(image)
        image.copy = original_copy  # type: ignore[assignment]
    return image, raw_original


class ImageMetadataError(IOError):
    pass


def get_mime_types(library: Library, paths: Sequence[str]) -> Sequence[str]:
    """Return a list containing the MIME type of each of the supplied file paths.

    :param library: The library containing all the files.
    :param paths: List of valid paths.
    """
    if not isinstance(library.storage, django_storage.FileSystemStorage):
        raise NotImplementedError(
            f"Image metadata loading is not implemented yet for storage backends "
            f"other than the filesystem backend (got {type(library.storage)!r} for "
            f"library {library.pk})."
        )

    try:
        exiftool_result = exiftool.execute_exiftool(
            "-MimeType",
            *(os.path.join(library.storage.base_location, path) for path in paths),
        )
    except (subprocess.CalledProcessError, exiftool.ExiftoolError) as error:
        raise ImageMetadataError(
            f"Failed to find MIME types for {len(paths)} file(s) in {library}."
        ) from error
    else:
        return [str(item.get("MIMEType", "")) for item in exiftool_result]


class ImageMetadata:
    """Metadata container that holds EXIF (and other) metadata of an image.

    This also supports
    """

    SIDECAR_MIME_TYPES: ClassVar[set[str]] = {"application/json", "application/rdf+xml"}

    def __init__(
        self, metadata: dict[str, Any], formatted_metadata: dict[str, Any]
    ) -> None:
        self._metadata = metadata
        self._formatted_metadata = formatted_metadata

        self._sidecar_format: Optional[tuple[Literal["google", "xmp"], str]] = None
        self._deriver_name: Optional[str] = None

        if (mime_type := self._get_string_value("MIMEType")).startswith("image/"):
            pass

        elif (
            mime_type == "application/json"
            and "googleusercontent.com" in self._get_string_value("Url")
            and self.file_basename.lower().endswith(".json")
        ):
            # This is a sidecar file downloaded from Google Photos. It contains a few
            # pieces of metadata that users can set from the UI. These have the same
            # filename as the actual image (plus the .json suffix).
            self._sidecar_format = ("google", self.file_basename[:-5])

        elif mime_type == "application/rdf+xml" and (
            deriver_name := self._get_string_value("DerivedFrom")
        ):
            # This is a sidecar file in XMP format, for example from darktable.
            self._sidecar_format = ("xmp", deriver_name)

        else:
            raise ValueError("unsupported file type")

    @staticmethod
    @functools.lru_cache(maxsize=settings.SCANNING_CACHE_SIZE)
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
        if not isinstance(library.storage, django_storage.FileSystemStorage):
            raise NotImplementedError(
                f"Image metadata loading is not implemented yet for storage backends "
                f"other than the filesystem backend (got {type(library.storage)!r} for "
                f"library {library.pk})."
            )

        try:
            exiftool_result = exiftool.execute_exiftool(
                "-n",
                os.path.join(library.storage.base_location, path),
            )
            formatted_exiftool_result = exiftool.execute_exiftool(
                "-d",
                "%Y-%m-%dT%H:%M:%S%6f",
                os.path.join(library.storage.base_location, path),
            )
        except (subprocess.CalledProcessError, exiftool.ExiftoolError) as error:
            raise ImageMetadataError(
                f"Cannot read image metadata in library {library.pk} for: {path}"
            ) from error
        else:
            try:
                return ImageMetadata(exiftool_result[0], formatted_exiftool_result[0])
            except ValueError as error:
                raise ImageMetadataError(
                    f"Cannot read image metadata in library {library.pk} for: {path}"
                ) from error

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

    @property
    def deriver_name(self) -> Optional[str]:
        """If this file is a sidecar file, this property points to the name of the
        actual image file this sidecar is holding metadata on."""
        return self._sidecar_format[1] if self._sidecar_format is not None else None

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

    file_basename = functools.cached_property(
        functools.partial(_get_string_value, key="FileName")
    )
    mime_type = functools.cached_property(
        functools.partial(_get_string_value, key="MIMEType")
    )
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

    @functools.cached_property
    def width(self) -> Optional[int]:
        return (
            self._get_integer_value("ImageWidth")
            or self._get_integer_value("OriginalImageWidth")
            or self._get_integer_value("ExifImageWidth")
            or self._get_integer_value("CanonImageWidth")
        )

    @functools.cached_property
    def height(self) -> Optional[int]:
        return (
            self._get_integer_value("ImageHeight")
            or self._get_integer_value("OriginalImageHeight")
            or self._get_integer_value("ExifImageHeight")
            or self._get_integer_value("CanonImageHeight")
        )

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


def calculate_blurhash(image: ImmutableImage) -> str:
    if settings.BLURHASH_SIZE < 1 or settings.BLURHASH_SIZE is None:
        raise ImproperlyConfigured("blurhash calculation has been disabled")

    # For the blurhash, make sure that the following is approximately true:
    # - BLURHASH_SIZE = a * b
    # - a / b = width / height
    # This distributes the requested size of the blurhash among the two axis
    # appropriately.
    b = math.sqrt(settings.BLURHASH_SIZE / image.width * image.height)
    a = b * image.width / image.height

    # Limit the components, so we stay inside the CharField's bounds.
    x_components = max(1, min(math.ceil(a), 8))
    y_components = max(1, min(math.ceil(b), 8))

    # Note that .convert() creates a copy. Therefore, calculate_blurhash operates on an
    # immutable input.
    thumbnail = image.convert("RGB")
    thumbnail.thumbnail(
        (x_components * 10, y_components * 10),
        PIL.Image.NEAREST,
    )

    return blurhash.encode(thumbnail, x_components, y_components)


def extract_timestamp_from_filename(path: str) -> Optional[datetime.datetime]:
    """Try to extract a timestamp from a filename."""
    try:
        basename = os.path.basename(path)
        return dateutil.parser.parse(basename, fuzzy=True, ignoretz=True)
    except ValueError:
        return None
