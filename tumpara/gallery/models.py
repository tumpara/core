from __future__ import annotations

from typing import Generic, TypeVar

from django.contrib.gis.db import models
from django.db import transaction
from django.db.models import expressions, functions
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from tumpara.accounts.models import AnonymousUser, User
from tumpara.libraries.models import File, RecordManager, RecordModel, RecordQuerySet

_GalleryRecord = TypeVar("_GalleryRecord", bound="GalleryRecord")


class GalleryRecordQuerySet(Generic[_GalleryRecord], RecordQuerySet[_GalleryRecord]):
    def for_user(
        self,
        permission: str,
        user: User | AnonymousUser,
    ) -> GalleryRecordQuerySet[_GalleryRecord]:
        return (
            super()
            .for_user(permission, user)
            .filter(
                models.Exists(
                    File.objects.filter(
                        record=models.OuterRef("pk"), availability__isnull=False
                    )
                )
            )
        )

    @transaction.atomic
    def stack(self) -> int:
        """Stack all records in this queryset together.

        After calling this method, all records will have the same stack key. If one or
        more record(s) is already in a stack, they will be merged into a single stack.
        """
        self._not_support_combined_queries("stack")
        if self.query.values_select or self.query.group_by:
            raise ValueError(
                "stacking is only supported on querysets that only filter and don't "
                "perform grouping"
            )

        # Find a stack key to use for the new (or merged) stack.
        stack_key = functions.Coalesce(
            # First, check and see if any of the items in our queryset already have a
            # stack key. In that case, use the smallest one, because they will all get
            # merged anyway.
            models.Subquery(
                self.order_by()  # Clear any initial order
                .filter(stack_key__isnull=False)
                # This trick with the dummy variable is from here:
                # https://stackoverflow.com/a/64902200
                # It removes the unnecessary GROUP BY clause that Django adds when using
                # annotate(). This should no longer be required once this ticket is
                # implemented: https://code.djangoproject.com/ticket/28296
                .annotate(dummy=models.Value(1))
                .values("dummy")
                .annotate(min_stack_key=models.Min("stack_key"))
                .values("min_stack_key")
            ),
            # If that didn't succeed, take the next free value in the database. While
            # this implementation doesn't strictly make sure that there isn't also a
            # smaller key that would also be available, it does ensure that we get a
            # key that isn't used yet and that is good enough.
            models.Subquery(
                GalleryRecord.objects
                # Clear out unneeded sorting and joins.
                .order_by()
                .select_related(None)
                # Here, we use the same trick as before to get rid of the grouping.
                .annotate(dummy=models.Value(1))
                .values("dummy")
                .values(new_stack_key=(models.Max("stack_key") + 1))
                .values("new_stack_key")
            ),
            # If we still don't have a stack key to use, then there aren't any stacks
            # in the database yet. In that case we can just start with an initial value.
            models.Value(1),
        )

        # Extract the first primary key from our queryset, because that will be the
        # new representative.
        representative_primary_key = self.values_list("pk")[:1]

        return GalleryRecord.objects.filter(
            models.Q(pk__in=self.values_list("pk"))
            | models.Q(stack_key__in=self.values_list("stack_key"))
        ).update(
            stack_key=stack_key,
            # Make the first item that was provided the representative. All others
            # will be "demoted".
            stack_representative=models.Case(
                models.When(pk=representative_primary_key, then=models.Value(True)),
                default=models.Value(False),
            ),
        )


GalleryRecordManager = RecordManager.from_queryset(GalleryRecordQuerySet)


class GalleryRecord(RecordModel):
    """Gallery records are a subset of all record types that can be displayed on a joint
    timeline.

    This model is intended for record types that can be considered some sort of personal
    media like photos, videos and other things it would make sense to put on a timeline.
    """

    media_timestamp = models.DateTimeField(
        _("media timestamp"),
        default=timezone.now,
        help_text=_(
            "Timestamp associated with the record's medium. For records without a "
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
            "Designates whether this records is its stack's representative. It "
            "will be shown as the cover element when the stack is rendered."
        ),
    )

    objects = GalleryRecordManager()

    class Meta:
        verbose_name = _("gallery record")
        verbose_name_plural = _("gallery records")
        db_table = "gallery_record"
        indexes = [
            models.Index(
                fields=("media_timestamp", "record"),
                name="timestamp_filtering",
            ),
            models.Index(
                fields=("media_location", "record"),
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


class GalleryRecordModel(GalleryRecord):
    gallery_record = models.OneToOneField(
        GalleryRecord,
        on_delete=models.CASCADE,
        primary_key=True,
        parent_link=True,
        related_name="%(class)s_instance",
        related_query_name="%(class)s_instance",
        verbose_name=_("gallery record reference"),
    )

    class Meta:
        abstract = True
