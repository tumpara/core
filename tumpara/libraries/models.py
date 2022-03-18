import os.path
from typing import Literal

from django.conf import settings
from django.contrib.contenttypes import fields as contenttypes_fields
from django.contrib.contenttypes import models as contenttypes_models
from django.core.files import base as django_files
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from tumpara.accounts import models as accounts_models

from . import storage


class Visibility:
    """Visibility settings shared by"""

    PUBLIC = 0
    INTERNAL = 1
    MEMBERS = 2
    OWNERS = 3

    VISIBILTY_CHOICES = [
        (PUBLIC, _("Public")),
        (INTERNAL, _("All logged-in users")),
        (MEMBERS, _("Library members")),
        (OWNERS, _("Only library owners")),
    ]


def validate_library_source(source: str) -> None:
    storage.backends.build(source).check()


class Library(accounts_models.Joinable):
    """A Library is a data source that supports scanning for files.

    Libraries hold content in form of :class:`Record` objects.
    """

    source = models.CharField(
        _("source"),
        unique=True,
        max_length=255,
        validators=[validate_library_source],
        help_text=_("URI for the configured storage backend."),
    )
    context = models.CharField(
        _("context"),
        max_length=50,
        help_text=_(
            "Context string that identifies the content types to expect in the library."
        ),
    )

    default_visibility = models.PositiveSmallIntegerField(
        _("default visibility"),
        choices=Visibility.VISIBILTY_CHOICES,
        default=Visibility.MEMBERS,
        help_text=_("Default visibility value for records where it is not defined."),
    )

    class Meta:
        verbose_name = _("library")
        verbose_name_plural = _("libraries")

    @cached_property
    def storage(self) -> storage.LibraryStorage:
        """The configured :class:`storage.LibraryStorage` for accessing files."""
        return storage.backends.build(self.source)

    @cached_property
    def _ignored_directories(self) -> set[str]:
        """Set of directories which should be ignored while scanning.

        This is built by going through the entire storage and looking for files named
        according to the ``DIRECTORY_IGNORE_FILENAME`` setting. All directories
        containing such a file are returned here.
        """
        result = set()
        if settings.DIRECTORY_IGNORE_FILENAME is not None:
            for path in self.storage.walk_files(safe=True):
                if os.path.basename(path) == settings.DIRECTORY_IGNORE_FILENAME:
                    result.add(os.path.dirname(path))
        return result

    def check_path_ignored(self, path: str) -> bool:
        """Check whether a given path should be ignored while scanning.

        If this method returns ``True``, no :class:`File` objects should be created for
        the path. It is assumed that directories are ignored recursively.
        """
        return any(
            # This part here is particularly error-prone. We basically want to check if
            # the given path starts with any of our ignored directories *plus* an extra
            # '/' (that's what the path.join is for), because it should only ignore
            # stuff actually in that directory. We don't want an ignored directory to
            # also take out sibling files with the same prefix.
            # Before we would use os.path.commonprefix, but that doesn't work because it
            # doesn't care about directories: commonprefix('/foo', '/foobar/test') will
            # be '/foo', which is exactly not what we want here.
            path.startswith(os.path.join(ignored_directory, ""))
            for ignored_directory in self._ignored_directories
        )


class Record(models.Model):
    """A piece of content in a library.

    This model's purpose is mainly to facilitate listing of all content in a library and
    provide a generalized permission model with visibility settings. The
    ``content_type`` and ``content_pk`` refer to the model that implements any
    actual content.

    Records may be linked to any number of :class:`File` objects. Although not strictly
    required (there may be library records that don't depend on a file), most will have
    at least one file.
    """

    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        verbose_name=_("library"),
        help_text=_(
            "Library the object is attached to. Users will have access depending on "
            "the visibility and their membership in this library."
        ),
    )
    visibility = models.PositiveSmallIntegerField(
        _("visibility"),
        choices=[
            *Visibility.VISIBILTY_CHOICES,
            (None, _("Use the library's default value")),
        ],
        null=True,
        default=None,
        help_text=_("Determines who can see this object."),
    )

    content_type = models.ForeignKey(
        contenttypes_models.ContentType, on_delete=models.CASCADE
    )
    object_pk = models.PositiveIntegerField()
    content_object = contenttypes_fields.GenericForeignKey("content_type", "object_pk")

    class Meta:
        verbose_name = _("library")
        verbose_name_plural = _("libraries")
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_pk"],
                name="record_unique_for_content_type",
            ),
        ]


class File(models.Model):
    """A file linked to a :class:`Record`."""

    record = models.ForeignKey(
        Record,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="files",
        related_query_name="file",
        verbose_name=_("library record"),
        help_text=_("The library record this file is attached to."),
    )

    path = models.CharField(
        _("filename"),
        max_length=255,
        db_index=True,
        help_text=_("Path of this file, relative to the library root."),
    )
    digest = models.CharField(
        _("digest value"),
        max_length=64,
        db_index=True,
        help_text="The file's cryptographic hash to quickly identify changes.",
    )
    availability = models.DateTimeField(
        _("last seen timestamp"),
        null=True,
        blank=True,
        help_text="Time the file was last deemed available to open. If this is unset, "
        "the file is known to be unavailable.",
    )

    class Meta:
        verbose_name = _("file")
        verbose_name_plural = _("files")
        constraints = [
            # Ideally, these would be unique per library, but Django doesn't currently
            # support constraints spanning relationships. Further, we only care about
            # unique paths. A digest may very well be present for multiple files in a
            # record, since we want copied files to both be attached to the same record.
            models.UniqueConstraint(
                fields=["record", "path"],
                condition=models.Q(availability__isnull=False),
                name="available_path_unique_per_record",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.path} in {self.record.library}"

    @property
    def directory_name(self) -> str:
        """Name of the directory the file is stored in, relative to the library root."""
        return os.path.dirname(self.path)

    def open(self, mode: Literal["r", "rb"] = "r") -> django_files.File:
        """Return an IO object for this file.

        :param mode: The file open mode – currently only reading is supported.
        """
        return self.record.library.storage.open(self.path, mode)
