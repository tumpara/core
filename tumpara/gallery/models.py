from __future__ import annotations

from typing import Generic, TypeVar, cast

from django.contrib.gis.db import models
from django.db import NotSupportedError, transaction
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
        queryset = cast(
            GalleryRecordQuerySet[_GalleryRecord], super().for_user(permission, user)
        )
        return queryset.filter(
            models.Exists(
                File.objects.filter(
                    record=models.OuterRef("pk"), availability__isnull=False
                )
            )
        )

    def _not_support_grouping(self, operation_name: str) -> None:
        self._not_support_combined_queries(operation_name)  # type: ignore
        if self.query.values_select or self.query.group_by:
            raise ValueError(
                f"calling {operation_name} is only supported on querysets that only "
                f"filter and don't perform grouping"
            )

    @transaction.atomic
    def stack(self) -> int:
        """Stack all records in this queryset together.

        After calling this method, all records will have the same stack key. If one or
        more record(s) is already in a stack, they will be merged into a single stack.

        :return: The new size of the stack.
        """
        self._not_support_grouping("stack")

        compiler = self.query.get_compiler(self.db)
        connection = compiler.connection

        selected_records_query, selected_records_params = compiler.compile(
            self.values("record_id", "stack_key", "stack_representative")
        )

        with connection.cursor() as cursor:
            records_table = GalleryRecord._meta.db_table
            cursor.execute(
                f"""
                WITH
                    selected_records AS ({selected_records_query}),

                    --- Choose a representative for the new stack.
                    chosen_representative AS (SELECT COALESCE(
                        --- If one the selected records is already a representative,
                        --- use that one.
                        (SELECT MIN(selected_records.record_id)
                         FROM selected_records
                         WHERE selected_records.stack_representative IS TRUE),
                        --- Otherwise broaden the search and take an existing
                        --- representative from the stacks that are already there.
                        (SELECT MIN("{records_table}".record_id)
                         FROM "{records_table}"
                         WHERE
                            "{records_table}".stack_representative IS TRUE
                            AND "{records_table}".stack_key IN (SELECT DISTINCT selected_records.stack_key from selected_records)),
                        --- If that still gives no result (because we are creating
                        --- completely new stacks), use the first record from our query.
                        (SELECT MIN(selected_records.record_id)
                         FROM selected_records)
                    ))
                UPDATE "{records_table}"
                SET
                    --- Find a stack key to use for the new (or merged) stack.
                    stack_key = COALESCE(
                        --- First, check and see if any of the items in our queryset
                        --- already have a stack key. In that case, use the smallest
                        --- one, because they will all get merged anyway.
                        (SELECT MIN(selected_records.stack_key)
                         FROM selected_records
                         WHERE selected_records.stack_key IS NOT NULL),
                        --- If that didn't succeed, take the next free value in the
                        --- database. While this implementation doesn't strictly make
                        --- sure that there isn't also a smaller key that would also be
                        --- available, it does ensure that we get a key that isn't used
                        --- yet and that is good enough.
                        (SELECT (MAX("{records_table}".stack_key) + 1)
                         FROM "{records_table}"),
                        --- If we still don't have a stack key to use, then there aren't
                        --- any stacks in the database yet. In that case we can just
                        --- start with an initial value.
                        1
                    ),

                    stack_representative = CASE
                        WHEN ("{records_table}".record_id IN (SELECT * FROM chosen_representative)) THEN TRUE
                        ELSE FALSE
                    END
                WHERE
                    "{records_table}".record_id IN (SELECT DISTINCT selected_records.record_id FROM selected_records)
                    OR "{records_table}".stack_key IN (SELECT DISTINCT selected_records.stack_key FROM selected_records)
                """,
                selected_records_params,
            )
            cursor.execute("SELECT CHANGES()")
            row = cursor.fetchone()

        return cast(int, row[0])

    def unstack(self) -> int:
        """Unstack all stacks matched by this queryset.

        Note that this will not merely remove the affected records from their stack, but
        will also unstack any other records in that stack. After calling this method,
        the corresponding stacks will no longer exist.

        :return: The size of the no longer existing stack.
        """
        self._not_support_grouping("stack")
        return GalleryRecord.objects.filter(
            stack_key__in=models.Subquery(
                self.filter(stack_key__isnull=False).values("stack_key").distinct()
            )
        ).update(stack_key=None, stack_representative=False)


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

    def represent_stack(self) -> None:
        """Make this record the representative of its stack."""
        if self.stack_key is None:
            raise NotSupportedError(
                "cannot set an unstacked record as a representative"
            )
        if self.stack_representative:
            return
        GalleryRecord.objects.filter(
            models.Q(pk=self.pk)
            | models.Q(stack_key=self.stack_key, stack_representative=True)
        ).update(
            stack_representative=models.Case(
                models.When(pk=self.pk, then=True), default=False
            )
        )
        self.stack_representative = True


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
