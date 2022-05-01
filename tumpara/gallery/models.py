from django.contrib.gis.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from tumpara.libraries.models import RecordModel


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

    class Meta:
        verbose_name = _("gallery record")
        verbose_name_plural = _("gallery records")
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
