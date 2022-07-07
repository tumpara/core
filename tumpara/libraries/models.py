from __future__ import annotations

import logging
import os.path
import uuid
from collections.abc import Iterator
from typing import Any, Generic, Literal, NoReturn, Optional, TypeVar, cast, overload

from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import EmptyResultSet, ValidationError
from django.core.files import base as django_files
from django.db import NotSupportedError, transaction
from django.db.models import functions
from django.db.models.query import ModelIterable  # type: ignore
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from tumpara.accounts.models import AnonymousUser, Joinable, JoinableQuerySet, User
from tumpara.accounts.utils import build_permission_name

from . import scanner, storage

_logger = logging.getLogger(__name__)


class Visibility:
    """Visibility settings shared by libraries and library assets."""

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

    Libraries hold content in form of :class:`Asset` objects.
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
        help_text=_("Default visibility value for assets where it is not defined."),
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

        This will make sure that all :class:`File` objects linked to an :class:`Asset`
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


_Asset = TypeVar("_Asset", bound="Asset")


class AssetQuerySet(Generic[_Asset], models.QuerySet[_Asset]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._resolve_instances = False

    # The following three methods are the replacements for __getitem__(), __iter__() and
    # get(). Instead of directly returning the models they were asked for, we call
    # resolve_instance() on the asset so that we get the actual subclass. Enable this
    # behaviour by using resolve_instances() on the queryset.
    # However, we can't directly override them, because then MyPy throws a fit. It seems
    # to have something to do with the Django plugin meddling with the method types on
    # the resulting managers, since the generics end up und some sort of unbound state.
    # But since it isn't really worth it to work around that properly we create these
    # new methods that do what we want them to do and patch them it later:

    @overload
    def _getitem(self, item: int) -> _Asset:
        ...

    @overload
    def _getitem(self, item: slice) -> AssetQuerySet[_Asset] | list[_Asset]:
        ...

    def _getitem(
        self, item: int | slice
    ) -> _Asset | AssetQuerySet[_Asset] | list[_Asset]:
        result = super().__getitem__(item)
        if not self._resolve_instances:
            return result

        assert self._iterable_class is ModelIterable  # type: ignore

        if isinstance(result, models.Model):
            assert isinstance(result, Asset)
            return cast(_Asset, result.resolve_instance())
        elif isinstance(result, list):
            assert all(isinstance(obj, Asset) for obj in result)  # type: ignore
            return cast(list[_Asset], [obj.resolve_instance() for obj in result])
        else:
            return cast(AssetQuerySet[_Asset], result)

    def _iter(self) -> Iterator[_Asset]:
        if not self._resolve_instances:
            yield from super().__iter__()
            return
        assert self._iterable_class is ModelIterable  # type: ignore
        for item in super().__iter__():
            assert isinstance(item, Asset)
            yield cast(_Asset, item.resolve_instance())

    def _get(self, *args: Any, **kwargs: Any) -> _Asset:
        result = super().get(*args, **kwargs)
        if not self._resolve_instances:
            return result
        assert self._iterable_class is ModelIterable  # type: ignore
        assert isinstance(result, Asset)
        return cast(_Asset, result.resolve_instance())

    def _clone(self) -> AssetQuerySet[_Asset]:
        clone = cast(AssetQuerySet[_Asset], super()._clone())  # type: ignore
        clone._resolve_instances = self._resolve_instances
        return clone

    # This is only so that we get a type annotation:
    def _chain(self) -> AssetQuerySet[_Asset]:
        return super()._chain()  # type: ignore

    def _not_support_grouping(self, operation_name: str) -> None:
        self._not_support_combined_queries(operation_name)  # type: ignore
        if self.query.values_select or self.query.group_by:
            raise ValueError(
                f"calling {operation_name} is only supported on querysets that only "
                f"filter and don't perform grouping"
            )

    def with_effective_visibility(self) -> AssetQuerySet[_Asset]:
        return self.alias(
            effective_visibility=models.Case(
                models.When(
                    visibility=Visibility.FROM_LIBRARY,
                    then=models.F("library__default_visibility"),
                ),
                default=models.F("visibility"),
            )
        )

    def resolve_instances(
        self, *prefetch_types: type[AssetModel]
    ) -> AssetQuerySet[_Asset]:
        """Return a queryset that returns concrete asset subclasses instead of the
        generic :class:`Asset` supertype.

        Pass subclasses of :class:`AssetModel` to automatically prefetch the
        corresponding tables, reducing the total number of database queries.
        """
        if (
            self._fields is not None  # type: ignore
            or self._iterable_class is not ModelIterable  # type: ignore
        ):
            raise NotSupportedError(
                "Calling AssetQuerySet.resolve_instances() is not supported after "
                ".values() or .values_list()."
            )
        self._not_support_grouping("resolve_instances")

        if prefetch_types:
            related_names = list[str]()
            for prefetch_type in prefetch_types:
                if not issubclass(prefetch_type, AssetModel):
                    raise TypeError(
                        f"automatic asset prefetching requires types to be "
                        f"subclasses of AssetModel, got {prefetch_type}"
                    )
                related_names.append(f"{prefetch_type._meta.model_name}_instance")
            clone = self.select_related(*related_names)
        else:
            clone = self._chain()
        clone._resolve_instances = True
        return clone

    def for_user(
        self,
        user: User | AnonymousUser,
        permission: str,
    ) -> AssetQuerySet[_Asset]:
        """Narrow down the queryset to only return elements where the given user has
        a specific permission."""

        if permission in (
            build_permission_name(Asset, "change"),
            build_permission_name(Asset, "delete"),
            build_permission_name(self.model, "change"),
            build_permission_name(self.model, "delete"),
        ):
            writing = True
        elif permission in (
            build_permission_name(Asset, "view"),
            build_permission_name(self.model, "view"),
        ):
            writing = False
        else:
            raise ValueError(f"unsupported permission: {permission}")

        if not user.is_authenticated:
            if writing:
                return self.none()
            else:
                return self.with_effective_visibility().filter(
                    effective_visibility=Visibility.PUBLIC
                )
        if not user.is_active:
            return self.none()
        if user.is_superuser:
            return self

        return self.filter(
            # Return assets with at least one available file or no files at all.
            # TODO In the future, each asset type should be able to specify whether we
            #  expect it to have files.
            (
                models.Exists(
                    File.objects.filter(
                        asset=models.OuterRef("pk"), availability__isnull=False
                    )
                )
                | ~models.Exists(File.objects.filter(asset=models.OuterRef("pk")))
            ),
            # Make sure we only return assets that the user can actually see. Note we
            # explicitly don't differentiate between the change and delete permission
            # because we want change_library to be the important one here:
            library__in=Library.objects.for_user(
                user,
                "libraries.change_library" if writing else "libraries.view_library",
            ),
        )

    @transaction.atomic
    def stack(self) -> int:
        """Stack all assets in this queryset together.

        After calling this method, all assets will have the same stack key. If one or
        more asset(s) is already in a stack, they will be merged into a single stack.

        :return: The new size of the stack.
        """
        self._not_support_grouping("stack")
        # Make sure we have one of the correct asset types. This is important to get the
        # primary keys correct later on.
        assert self.model is Asset or issubclass(self.model, AssetModel), (
            "AssetManager methods are intended to be used on Asset.objects or a "
            "subclass of AssetModel."
        )

        compiler = self.query.get_compiler(self.db)
        connection = compiler.connection

        try:
            selected_assets_query, selected_assets_params = compiler.compile(
                self.values(
                    "stack_key",
                    "stack_representative",
                    # Hoist out the primary key into a new field name because for the
                    # base Asset class it's called "id" and for subclasses its called
                    # "asset_id" (see the AssetModel class).
                    actual_asset_id=models.F("pk"),
                ).query
            )
        except EmptyResultSet:
            # This case occurs when we try to stack an empty queryset,for example
            # because the permission filtering logic explicitly returned .none().
            return 0

        with connection.cursor() as cursor:
            assets_table = Asset._meta.db_table
            cursor.execute(
                f"""
                WITH
                    selected_assets AS ({selected_assets_query}),

                    --- Choose a representative for the new stack.
                    chosen_representative AS (SELECT COALESCE(
                        --- If one the selected assets is already a representative,
                        --- use that one.
                        (SELECT MIN(selected_assets.actual_asset_id)
                         FROM selected_assets
                         WHERE selected_assets.stack_representative IS TRUE),
                        --- Otherwise broaden the search and take an existing
                        --- representative from the stacks that are already there.
                        (SELECT MIN("{assets_table}".id)
                         FROM "{assets_table}"
                         WHERE
                            "{assets_table}".stack_representative IS TRUE
                            AND "{assets_table}".stack_key IN (SELECT DISTINCT selected_assets.stack_key from selected_assets)),
                        --- If that still gives no result (because we are creating
                        --- completely new stacks), use the first asset from our query.
                        (SELECT MIN(selected_assets.actual_asset_id)
                         FROM selected_assets)
                    ))
                UPDATE "{assets_table}"
                SET
                    --- Find a stack key to use for the new (or merged) stack.
                    stack_key = COALESCE(
                        --- First, check and see if any of the items in our queryset
                        --- already have a stack key. In that case, use the smallest
                        --- one, because they will all get merged anyway.
                        (SELECT MIN(selected_assets.stack_key)
                         FROM selected_assets
                         WHERE selected_assets.stack_key IS NOT NULL),
                        --- If that didn't succeed, take the next free value in the
                        --- database. While this implementation doesn't strictly make
                        --- sure that there isn't also a smaller key that would also be
                        --- available, it does ensure that we get a key that isn't used
                        --- yet and that is good enough.
                        (SELECT (MAX("{assets_table}".stack_key) + 1)
                         FROM "{assets_table}"),
                        --- If we still don't have a stack key to use, then there aren't
                        --- any stacks in the database yet. In that case we can just
                        --- start with an initial value.
                        1
                    ),

                    stack_representative = CASE
                        WHEN ("{assets_table}".id IN (SELECT * FROM chosen_representative)) THEN TRUE
                        ELSE FALSE
                    END
                WHERE
                    "{assets_table}".id IN (SELECT DISTINCT selected_assets.actual_asset_id FROM selected_assets)
                    OR "{assets_table}".stack_key IN (SELECT DISTINCT selected_assets.stack_key FROM selected_assets)
                """,
                selected_assets_params,
            )
            cursor.execute("SELECT CHANGES()")
            row = cursor.fetchone()

        return cast(int, row[0])

    def unstack(self) -> int:
        """Unstack all stacks matched by this queryset.

        Note that this will not merely remove the affected assets from their stack, but
        will also unstack any other assets in that stack. After calling this method,
        the corresponding stacks will no longer exist.

        :return: The size of the no longer existing stack.
        """
        self._not_support_grouping("stack")
        stack_size = Asset.objects.filter(
            stack_key__in=models.Subquery(
                self.filter(stack_key__isnull=False).values("stack_key").distinct()
            )
        ).update(stack_key=None, stack_representative=False)
        return cast(int, stack_size)


# Patch the methods related to getting instance methods with the new counterparts (see
# the comment above for details).
AssetQuerySet.__getitem__ = AssetQuerySet._getitem  # type: ignore
AssetQuerySet.__iter__ = AssetQuerySet._iter  # type: ignore
AssetQuerySet.get = AssetQuerySet._get  # type: ignore

AssetManager = models.Manager.from_queryset(AssetQuerySet)


class Asset(models.Model):
    """A piece of content in a library.

    This model's purpose is mainly to facilitate listing of all content in a library and
    provide a generalized permission model with visibility settings. Assets that hold
    actual content should be implemented by subclassing :class:`AssetModel`.

    Assets may be linked to any number of :class:`File` objects. Although not strictly
    required (there may be library assets that don't depend on a file), most will have
    at least one file.

    Most metadata will be stored in the subclass' model. However, this base class also
    contains a number of attributes that might be applicable for most asset types.
    """

    uuid = models.UUIDField(
        _("UUID"),
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name="assets",
        related_query_name="asset",
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
        help_text=_("Timestamp when the asset was created / imported."),
    )

    media_timestamp = models.DateTimeField(
        _("media timestamp"),
        null=True,
        blank=True,
        help_text=_(
            "Timestamp associated with the asset's medium. This will mostly be set for "
            "assets with files."
        ),
    )

    media_location = models.PointField(
        _("media location"),
        null=True,
        blank=True,
        help_text=_("Real-world location associated with this entry."),
    )

    # The reason we don't use a single foreign key that points to the representative
    # directly is because this approach lets us define more precise database
    # constraints (see the Meta class below).
    stack_key = models.PositiveIntegerField(
        _("stack key"),
        null=True,
        blank=True,
        default=None,
        help_text=_("Identifier that is the same for all entries on a stack."),
    )
    stack_representative = models.BooleanField(
        _("stack representative status"),
        default=False,
        help_text=_(
            "Designates whether this asset is its stack's representative. It will be "
            "shown as the cover element when the stack is rendered."
        ),
    )

    objects = AssetManager()

    class Meta:
        verbose_name = _("asset")
        verbose_name_plural = _("assets")
        get_latest_by = "media_timestamp"
        ordering = [functions.Coalesce("media_timestamp", "import_timestamp")]
        indexes = [
            models.Index(
                fields=("id", "visibility", "library"),
                name="library_visibility_filtering",
            ),
            models.Index(
                fields=("visibility", "library", "media_timestamp"),
                name="timestamp_filtering",
            ),
            models.Index(
                fields=("visibility", "library", "media_location"),
                name="location_filtering",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("stack_key", "stack_representative"),
                condition=models.Q(stack_representative=True),
                name="unique_representative_per_stack",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(stack_key__isnull=False)
                    | models.Q(stack_representative=False)
                ),
                name="not_a_representative_when_unstacked",
            ),
        ]

    def resolve_instance(self, *, recursive: bool = True) -> Asset:
        """Resolve the actual instance of this asset.

        This will go through all known subclasses and see which type implements the
        asset. Performance-wise this is very much suboptimal, as a lot of database
        queries are required. It is recommended to call this on models coming from a
        queryset where :meth:`models.QuerySet.select_related` was used to prefetch
        data for the concrete :class:`Asset` implementations.

        Further, note that this assumes that subclasses add a related descriptor on this
        parent class named something like ``photo_instance``. This is done automatically
        by subclassing :class:`AssetModel` instead of :class:`Asset` directly.

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
                subtype = cast(Asset, getattr(self, field.name))
                return subtype.resolve_instance() if recursive else subtype
            except field.related_model.DoesNotExist:
                pass

        # We found nothing, so let's go with the instance we already have.
        return self

    def represent_stack(self, commit: bool = True) -> None:
        """Make this asset the representative of its stack.

        :param commit: Set this to ``False`` to disable saving of the model.
        """
        if self.stack_key is None:
            raise NotSupportedError("cannot set an unstacked asset as a representative")
        if self.stack_representative:
            return
        Asset.objects.filter(
            models.Q(pk=self.pk)
            | models.Q(stack_key=self.stack_key, stack_representative=True)
        ).update(
            stack_representative=models.Case(
                models.When(pk=self.pk, then=True), default=False
            )
        )
        self.stack_representative = True
        if commit:
            self.save()


class AssetModel(Asset):
    asset = models.OneToOneField(
        Asset,
        on_delete=models.CASCADE,
        primary_key=True,
        parent_link=True,
        related_name="%(class)s_instance",
        related_query_name="%(class)s_instance",
        verbose_name=_("asset reference"),
    )

    class Meta:
        abstract = True


class File(models.Model):
    """A file linked to an :class:`Asset`."""

    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        db_index=True,
        related_name="files",
        related_query_name="file",
        verbose_name=_("library asset"),
        help_text=_("The library asset this file is attached to."),
    )

    path = models.CharField(
        _("filename"),
        max_length=255,
        db_index=True,
        help_text=_(
            "Path of this file, relative to the library root. This should *not* "
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
            # asset, since we want copied files to both be attached to the same asset.
            models.UniqueConstraint(
                fields=["asset", "path"],
                condition=models.Q(availability__isnull=False),
                name="path_unique_per_asset",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.path} in {self.asset.library}"

    @property
    def library(self) -> Library:
        return self.asset.library

    @property
    def available(self) -> bool:
        return self.availability is not None

    @property
    def directory_name(self) -> str:
        """Name of the directory the file is stored in, relative to the library root."""
        return os.path.dirname(self.path)

    def open(self, mode: Literal["r", "rb"] = "r") -> django_files.File:  # type: ignore
        """Return an IO object for this file.

        :param mode: The file open mode – currently only reading is supported.
        """
        return self.asset.library.storage.open(self.path, mode)


class CollectionQuerySet(JoinableQuerySet["Collection"]):
    pass


CollectionManager = models.Manager.from_queryset(CollectionQuerySet)


class Collection(Joinable):
    """Collections allow users to sort and categorize assets.

    They are joinable, meaning users can add others and allow them to also view content
    in the collection. These permissions are transitive, meaning that assets from
    collections a user is invited to are also visible in their timeline.
    """

    title = models.CharField(
        _("title"),
        max_length=250,
        help_text=_("Title of the collection."),
    )

    assets = models.ManyToManyField(
        Asset,
        through="CollectionItem",
        related_name="collections",
        related_query_name="collection",
    )

    objects = CollectionManager()

    class Meta:
        verbose_name = _("collection")
        verbose_name_plural = _("collection")
        ordering = ("title",)


class CollectionItem(models.Model):
    """Reference of an asset inside a collection."""

    collection = models.ForeignKey(
        Collection,
        on_delete=models.CASCADE,
        verbose_name=_("collection"),
        help_text=_("The collection the asset is placed in."),
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        verbose_name=_("asset"),
        help_text=_("The asset to place in the collection."),
    )


class Note(AssetModel):
    """A note is the simplest asset type available in the gallery.

    It represents a user-defined short (or long) text that should be rendered as
    markdown.
    """

    content = models.TextField(
        _("note content"),
        help_text=_(
            "Content of the note, which should be rendered using the markdown syntax."
        ),
    )

    objects: AssetManager[Note]

    class Meta:
        verbose_name = _("note")
        verbose_name_plural = _("notes")
