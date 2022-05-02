from __future__ import annotations

from typing import Generic, TypeVar

from django.contrib.gis.db import models
from django.db import transaction
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

        # Update the stack keys so the provided objects are on the same stack. What we
        # need to do here:
        # 1) Find all the stacks that contain at least one of the provided objects -
        #    these are the stacks that will be relevant later.
        # 2) Find a key for the stack that will be set. This is either one of the ones
        #    we discovered before, or the next free one.
        # 3) Update the stack key for all applicable entries. This includes both those
        #    provided by the caller and those in the existing stacks (since we want to
        #    merge them).
        # Find all the stacks that contain at least one of the provided objects - these
        # are the keys that will be relevant later.
        relevant_stack_keys = {item[0] for item in self.values_list("stack_key")} - {
            None
        }

        if len(relevant_stack_keys) == 0:
            # If none of the objects is in a stack yet, we need a new key. This will
            # be the next available one. In order to avoid race conditions, we use
            # a subquery here.
            new_stack_key = models.RawSQL(
                f"""
                SELECT COALESCE(MAX(stack_key) + 1, 1)
                FROM {GalleryRecord._meta.db_table}
                """,
                (),
            )
        else:
            # If we already have an existing stack, we can use a key from there.
            new_stack_key = min(relevant_stack_keys)

        queryset = GalleryRecord.objects.filter(
            models.Q(pk__in=self.values_list("pk"))
            | models.Q(stack_key__in=relevant_stack_keys)
        )

        # If any of the existing entries was a representative before, use that.
        # Otherwise choose the first one.
        # representative_primary_key = self.values_list("pk").first()[0]
        representative_primary_key = models.Subquery(
            self
            # Using .order_by() with empty arguments here to remove the initial
            # ordering by timestamp:
            .order_by()
            # This trick with the dummy variable is from here:
            # https://stackoverflow.com/a/64902200
            # It removes the unnecessary GROUP BY clause that Django adds
            # when using .annotate(). This should no longer be required once
            # this ticket is implemented:
            # https://code.djangoproject.com/ticket/28296
            .annotate(dummy=models.Value(1))
            .values("dummy")
            .annotate(new_visibility=models.Min("pk"))
            .values("new_visibility"),
        )

        return queryset.update(
            stack_key=new_stack_key,
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
    stack_key = models.IntegerField(
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
