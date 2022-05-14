from __future__ import annotations

from typing import Any  # noqa: F401
from typing import Generic, TypeVar, cast

from django.contrib.gis.db import models
from django.core.exceptions import EmptyResultSet
from django.db import NotSupportedError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from tumpara.accounts.models import AnonymousUser, User
from tumpara.libraries.models import AssetManager, AssetModel, AssetQuerySet, File

_GalleryAsset = TypeVar("_GalleryAsset", bound="GalleryAsset")


class GalleryAssetQuerySet(Generic[_GalleryAsset], AssetQuerySet[_GalleryAsset]):
    def resolve_instances(  # type: ignore
        self, *prefetch_types: type[GalleryAssetModel]
    ) -> GalleryAssetQuerySet[_GalleryAsset]:
        for prefetch_type in prefetch_types:
            if not issubclass(prefetch_type, GalleryAssetModel):
                raise TypeError(
                    f"automatic asset prefetching requires types to be "
                    # We only override the method so this error message is more verbose:
                    f"subclasses of GalleryAssetModel, got {prefetch_type}"
                )
        return cast(
            GalleryAssetQuerySet[_GalleryAsset],
            super().resolve_instances(*prefetch_types),
        )

    def for_user(
        self,
        user: User | AnonymousUser,
        permission: str,
    ) -> GalleryAssetQuerySet[_GalleryAsset]:
        # Rewrite the permission string so .for_user() from the superclass understands
        # it.
        if permission in (
            "gallery.change_galleryasset",
            "gallery.delete_galleryasset",
            "gallery.view_galleryasset",
        ):
            permission = f"libraries.{permission[8:][:-14]}_asset"

        queryset = (
            super()
            .for_user(user, permission)
            .filter(
                # Either we have at least one available file or no files at all.
                # TODO This could probably be cleaner, depending on whether we expect files.
                models.Exists(
                    File.objects.filter(
                        asset=models.OuterRef("pk"), availability__isnull=False
                    )
                )
                | ~models.Exists(File.objects.filter(asset=models.OuterRef("pk")))
            )
        )
        return cast(GalleryAssetQuerySet[_GalleryAsset], queryset)

    @transaction.atomic
    def stack(self) -> int:
        """Stack all assets in this queryset together.

        After calling this method, all assets will have the same stack key. If one or
        more asset(s) is already in a stack, they will be merged into a single stack.

        :return: The new size of the stack.
        """
        self._not_support_grouping("stack")

        compiler = self.query.get_compiler(self.db)
        connection = compiler.connection

        try:
            selected_assets_query, selected_assets_params = compiler.compile(
                self.values("asset_id", "stack_key", "stack_representative").query
            )
        except EmptyResultSet:
            # This case occurs when we try to stack an empty queryset,for example
            # because the permission filtering logic explicitly returned .none().
            return 0

        with connection.cursor() as cursor:
            assets_table = GalleryAsset._meta.db_table
            cursor.execute(
                f"""
                WITH
                    selected_assets AS ({selected_assets_query}),

                    --- Choose a representative for the new stack.
                    chosen_representative AS (SELECT COALESCE(
                        --- If one the selected assets is already a representative,
                        --- use that one.
                        (SELECT MIN(selected_assets.asset_id)
                         FROM selected_assets
                         WHERE selected_assets.stack_representative IS TRUE),
                        --- Otherwise broaden the search and take an existing
                        --- representative from the stacks that are already there.
                        (SELECT MIN("{assets_table}".asset_id)
                         FROM "{assets_table}"
                         WHERE
                            "{assets_table}".stack_representative IS TRUE
                            AND "{assets_table}".stack_key IN (SELECT DISTINCT selected_assets.stack_key from selected_assets)),
                        --- If that still gives no result (because we are creating
                        --- completely new stacks), use the first asset from our query.
                        (SELECT MIN(selected_assets.asset_id)
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
                        WHEN ("{assets_table}".asset_id IN (SELECT * FROM chosen_representative)) THEN TRUE
                        ELSE FALSE
                    END
                WHERE
                    "{assets_table}".asset_id IN (SELECT DISTINCT selected_assets.asset_id FROM selected_assets)
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
        stack_size = GalleryAsset.objects.filter(
            stack_key__in=models.Subquery(
                self.filter(stack_key__isnull=False).values("stack_key").distinct()
            )
        ).update(stack_key=None, stack_representative=False)
        return cast(int, stack_size)


GalleryAssetManager = AssetManager.from_queryset(GalleryAssetQuerySet)


class GalleryAsset(AssetModel):
    """Gallery assets are a subset of all asset types that can be displayed on a joint
    timeline.

    This model is intended for asset types that can be considered some sort of personal
    media like photos, videos and other things it would make sense to put on a timeline.
    """

    media_timestamp = models.DateTimeField(
        _("media timestamp"),
        default=timezone.now,
        help_text=_(
            "Timestamp associated with the asset's medium. For assets without a "
            "media file, this should be the creation date."
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
            "Designates whether this asset is its stack's representative. It "
            "will be shown as the cover element when the stack is rendered."
        ),
    )

    objects = GalleryAssetManager()

    class Meta:
        verbose_name = _("gallery asset")
        verbose_name_plural = _("gallery assets")
        db_table = "gallery_asset"
        get_latest_by = "media_timestamp"
        ordering = ("media_timestamp",)
        indexes = [
            models.Index(
                fields=("media_timestamp", "asset"),
                name="timestamp_filtering",
            ),
            models.Index(
                fields=("media_location", "asset"),
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

    def represent_stack(self, commit: bool = True) -> None:
        """Make this asset the representative of its stack.

        :param commit: Set this to ``False`` to disable saving of the model.
        """
        if self.stack_key is None:
            raise NotSupportedError("cannot set an unstacked asset as a representative")
        if self.stack_representative:
            return
        GalleryAsset.objects.filter(
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


class GalleryAssetModel(GalleryAsset):
    gallery_asset = models.OneToOneField(
        GalleryAsset,
        on_delete=models.CASCADE,
        primary_key=True,
        parent_link=True,
        related_name="%(class)s_instance",
        related_query_name="%(class)s_instance",
        verbose_name=_("gallery asset reference"),
    )

    class Meta:
        abstract = True


class Note(GalleryAssetModel):
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
