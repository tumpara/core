from __future__ import annotations

import logging
import os.path
import uuid
from collections.abc import Iterator
from typing import Any, Generic, Literal, NoReturn, Optional, TypeVar, cast, overload

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import base as django_files
from django.db import models
from django.db.models.query import ModelIterable
from django.db.utils import NotSupportedError
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from tumpara.accounts.models import AnonymousUser, Joinable, JoinableQuerySet, User
from tumpara.accounts.utils import build_permission_name

from . import scanner, storage

_logger = logging.getLogger(__name__)


class Visibility:
    """Visibility settings shared by libraries and library records."""

    PUBLIC = 0
    INTERNAL = 1
    MEMBERS = 2
    OWNERS = 3
    FROM_LIBRARY = 10

    VISIBILTY_CHOICES = [
        (PUBLIC, _("Public")),
        (INTERNAL, _("All logged-in users")),
        (MEMBERS, _("Library members")),
        (OWNERS, _("Only library owners")),
        (FROM_LIBRARY, _("Use the default value")),
    ]


def validate_library_source(source: str) -> None:
    storage.backends.build(source).check()


def validate_library_default_visibility(value: int) -> None:
    if value == Visibility.FROM_LIBRARY:
        raise ValidationError(
            "Libraries cannot take visibility values from themselves.",
            code="no-recursive-library-visibility",
        )


class LibraryQuerySet(JoinableQuerySet["Library"]):
    pass


LibraryManager = models.Manager.from_queryset(LibraryQuerySet)


class Library(Joinable):
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
        validators=[validate_library_default_visibility],
        help_text=_("Default visibility value for records where it is not defined."),
    )

    objects = LibraryManager()

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

    @overload
    def scan(
        self, watch: Literal[False] = False, *, thread_count: Optional[int] = ...
    ) -> None:
        ...

    @overload
    def scan(
        self, watch: Literal[True], *, thread_count: Optional[int] = ...
    ) -> NoReturn:
        ...

    def scan(self, watch: bool = False, *, thread_count: Optional[int] = None) -> Any:
        """Perform a full scan of file in this library.

        This will make sure that all :class:`File` objects linked to a :class:`Record`
        of this library are up-to-date. However, that does not mean that all files in
        the database are actually readable - implementors are advised to check whether
        the :attr:`File.availability` attribute is `None` and act accordingly.

        :param watch: Whether to continue to watch for changes after the initial scan
            has been completed. If this is set, this function will not return and idle
            until new events come in.
        :param thread_count: Number of processes to use for event handling. If this is
            `None` (the default), a sane default will automatically be chosen.
        """
        _logger.info(
            f"Scanning step 1 of 3 for {self}: Checking for ignored directories..."
        )
        try:
            del self._ignored_directories
        except AttributeError:
            pass
        self.check_path_ignored("/")
        _logger.debug(
            f"Found {len(self._ignored_directories)} folder(s) that will be ignored "
            f"while scanning."
        )

        scan_event = scanner.ScanEvent()

        def scan_events() -> storage.WatchGenerator:
            for path in self.storage.walk_files(safe=True):
                yield scanner.FileModifiedEvent(path=path)

        _logger.info(f"Scanning step 2 of 3 for {self}: Searching for new content...")
        scanner.run(self, scan_events(), thread_count=thread_count)

        _logger.info(
            f"Scanning step 3 of 3 for {self}: Removing obsolete database entries..."
        )
        scan_event.commit(self)

        if not watch:
            _logger.info(f"Finished scan for {self}.")
            return
        _logger.info(
            f"Finished file scan for {self}. Continuing to watch for changes..."
        )

        def watch_events() -> storage.WatchGenerator:
            # When watching, pass through all events from the storage backend's
            # EventGenerator. The response needs to be handled separately to support
            # stopping the generator.
            generator = self.storage.watch()
            response: Literal[None, False] | int = None
            while response is not False:
                response = yield generator.send(response)
            try:
                generator.send(False)
            except StopIteration:
                pass

        scanner.run(self, watch_events(), thread_count=thread_count)


_Record = TypeVar("_Record", bound="Record")
_RecordQuerySet = TypeVar("_RecordQuerySet", bound="RecordQuerySet[Any]")


class RecordQuerySet(Generic[_Record], models.QuerySet[_Record]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._resolve_instances = False

    @overload
    def __getitem__(self, item: int) -> _Record:
        ...

    @overload
    def __getitem__(
        self: _RecordQuerySet, item: slice
    ) -> _RecordQuerySet | list[_Record]:
        ...

    def __getitem__(
        self: _RecordQuerySet, item: int | slice
    ) -> _Record | _RecordQuerySet | list[_Record]:
        result = super().__getitem__(item)
        if not self._resolve_instances:
            return result

        assert self._iterable_class is ModelIterable

        if isinstance(result, models.Model):
            assert isinstance(result, Record)
            return result.resolve_instance()
        elif isinstance(result, list):
            assert all(isinstance(obj, Record) for obj in result)
            return [obj.resolve_instance() for obj in result]
        else:
            return result

    def __iter__(self) -> Iterator[_Record]:
        if not self._resolve_instances:
            yield from super().__iter__()
            return
        assert self._iterable_class is ModelIterable
        for item in super().__iter__():
            assert isinstance(item, Record)
            yield item.resolve_instance()

    def get(self, *args, **kwargs) -> _Record:
        result = super().get(*args, **kwargs)
        if not self._resolve_instances:
            return result
        assert self._iterable_class is ModelIterable
        assert isinstance(result, Record)
        return result.resolve_instance()

    def _clone(self: _RecordQuerySet) -> _RecordQuerySet:
        clone = super()._clone()
        clone._resolve_instances = self._resolve_instances
        return clone

    def _not_support_grouping(self, operation_name: str) -> None:
        self._not_support_combined_queries(operation_name)  # type: ignore
        if self.query.values_select or self.query.group_by:
            raise ValueError(
                f"calling {operation_name} is only supported on querysets that only "
                f"filter and don't perform grouping"
            )

    def resolve_instances(
        self: _RecordQuerySet, *prefetch_types: type[RecordModel]
    ) -> _RecordQuerySet:
        """Return a queryset that returns concrete record subclasses instead of the
        generic :class:`Record` supertype.

        Pass subclasses of :class:`RecordModel` to automatically prefetch the
        corresponding tables, reducing the total number of database queries.
        """
        if self._fields is not None or self._iterable_class is not ModelIterable:
            raise NotSupportedError(
                "Calling RecordQuerySet.resolve_instances() is not supported after "
                ".values() or .values_list()."
            )
        self._not_support_grouping("resolve_instances")

        if prefetch_types:
            related_names = list[str]()
            for prefetch_type in prefetch_types:
                if not issubclass(prefetch_type, RecordModel):
                    raise TypeError(
                        f"automatic record prefetching requires types to be "
                        f"subclasses of RecordModel, got {prefetch_type}"
                    )
                related_names.append(f"{prefetch_type._meta.model_name}_instance")
            clone = self.select_related(*related_names)
        else:
            clone = self._chain()
        clone._resolve_instances = True
        return clone

    def for_user(
        self: _RecordQuerySet,
        user: User | AnonymousUser,
        permission: str,
    ) -> _RecordQuerySet:
        """Narrow down the queryset to only return elements where the given user has
        a specific permission."""
        if not user.is_authenticated or not user.is_active:
            return self.none()
        if user.is_superuser:
            return self

        if permission in (
            build_permission_name(self.model, "change"),
            build_permission_name(self.model, "delete"),
        ):
            # We explicitly don't differentiate between the change and delete permission
            # because we want change_library to be the important one here:
            return self.filter(
                library__in=Library.objects.for_user(user, "libraries.change_library")
            )
        elif permission == build_permission_name(self.model, "view"):
            return self.filter(
                library__in=Library.objects.for_user(user, "libraries.view_library")
            )
        else:
            raise ValueError(f"unsupported permission: {permission}")


RecordManager = models.Manager.from_queryset(RecordQuerySet)


class Record(models.Model):
    """A piece of content in a library.

    This model's purpose is mainly to facilitate listing of all content in a library and
    provide a generalized permission model with visibility settings. Records that hold
    actual content should be implemented by subclassing :class:`RecordModel`.

    Records may be linked to any number of :class:`File` objects. Although not strictly
    required (there may be library records that don't depend on a file), most will have
    at least one file.
    """

    uuid = models.UUIDField(
        _("UUID"), default=uuid.uuid4, editable=False, unique=True, db_index=True
    )

    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name="records",
        related_query_name="record",
        verbose_name=_("library"),
        help_text=_(
            "Library the object is attached to. Users will have access depending on "
            "the visibility and their membership in this library."
        ),
    )

    visibility = models.PositiveSmallIntegerField(
        _("visibility"),
        choices=Visibility.VISIBILTY_CHOICES,
        default=Visibility.FROM_LIBRARY,
        help_text=_("Determines who can see this object."),
    )

    import_timestamp = models.DateTimeField(
        _("add timestamp"),
        auto_now_add=True,
        help_text=_("Timestamp when the record was created / imported."),
    )

    objects = RecordManager()

    class Meta:
        verbose_name = _("record")
        verbose_name_plural = _("records")
        indexes = [
            models.Index(
                fields=("id", "visibility", "library"),
                name="library_visibility_filtering",
            )
        ]

    def resolve_instance(self, *, recursive: bool = True) -> Record:
        """Resolve the actual instance of this record.

        This will go through all known subclasses and see which type implements the
        record. Performance-wise this is very much suboptimal, as a lot of database
        queries are required. It is recommended to call this on models coming from a
        queryset where :meth:`models.QuerySet.select_related` was used to prefetch
        data for the concrete :class:`Record` implementations.

        Further note that this assumes that subclasses add a related descriptor on this
        parent class named something like ``photo_instance``. This is done automatically
        by subclassing :class:`RecordModel` instead of :class:`Record` directly.

        :param recursive: By default, instances are resolved recursively. Set this to
            ``False`` to only resolve the first child.
        """
        for field in self._meta.get_fields():
            if not (
                field.name.endswith("_instance")
                and isinstance(field, models.OneToOneRel)
                and issubclass(field.related_model, type(self))
            ):
                # This field is not applicable because it is not the other side of a
                # OneToOneField from a subclass with parent_link set.
                continue
            try:
                subtype = cast(Record, getattr(self, field.name))
                return subtype.resolve_instance() if recursive else subtype
            except field.related_model.DoesNotExist:
                pass

        # We found nothing, so let's go with the instance we already have.
        return self


class RecordModel(Record):
    record = models.OneToOneField(
        Record,
        on_delete=models.CASCADE,
        primary_key=True,
        parent_link=True,
        related_name="%(class)s_instance",
        related_query_name="%(class)s_instance",
        verbose_name=_("record reference"),
    )

    class Meta:
        abstract = True


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
        help_text=_(
            "Path of this file, relative to the library root. This should *not*"
            "start with a slash."
        ),
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
                name="path_unique_per_record",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.path} in {self.record.library}"

    @property
    def library(self) -> Library:
        return self.record.library

    @property
    def available(self) -> bool:
        return self.availability is not None

    @property
    def directory_name(self) -> str:
        """Name of the directory the file is stored in, relative to the library root."""
        return os.path.dirname(self.path)

    def open(self, mode: Literal["r", "rb"] = "r") -> django_files.File:
        """Return an IO object for this file.

        :param mode: The file open mode – currently only reading is supported.
        """
        return self.record.library.storage.open(self.path, mode)
