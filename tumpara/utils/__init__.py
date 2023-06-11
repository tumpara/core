import datetime
import os
import shutil
from typing import Optional

from django.conf import settings


def clean_storages() -> None:
    """Cleanup all storages filled by Tumpara."""
    shutil.rmtree(settings.THUMBNAIL_STORAGE.base_location)
    os.mkdir(settings.THUMBNAIL_STORAGE.base_location)


def precisest_datetime(
    a: Optional[datetime.datetime],
    b: Optional[datetime.datetime],
    *,
    prefer_later: bool = False,
) -> Optional[datetime.datetime]:
    """Return the more precise of the two timestamps.

    :param a: The first timestamp to compare.
    :param b: The second timestamp to compare.
    :param prefer_later: By default, the earlier of the two inputs is returned, if they
        are otherwise equally relevant. Set this to :obj:`True` to prefer higher values
        instead.
    """
    # Check if either is None or the epoch, in which case it will be ignored.
    if a is None or a.timestamp() == 0:
        if b is None or b.timestamp() == 0:
            return None
        else:
            return b
    elif b is None or b.timestamp() == 0:
        return a

    # Prefer datetimes with microsecond-level precision.
    elif a.microsecond and not b.microsecond:
        return a
    elif b.microsecond and not a.microsecond:
        return b

    # Prefer datetimes with timezone information.
    elif a.tzinfo and not b.tzinfo:
        return a
    elif b.tzinfo and not a.tzinfo:
        return b

    elif prefer_later:
        return max(a, b)
    else:
        return min(a, b)
