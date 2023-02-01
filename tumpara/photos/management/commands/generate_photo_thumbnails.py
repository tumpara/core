from __future__ import annotations

import logging
import multiprocessing
from typing import Any

import django
from django.core import management
from django.db import connection, models

from tumpara.libraries.scanner.runner import check_thread_count

_logger = logging.getLogger(__name__)


def worker(photo_pk_queue: multiprocessing.JoinableQueue[int]) -> None:
    django.setup()
    from tumpara.photos.views import AVIF_SUPPORTED, _get_thumbnail_path

    while True:
        photo_pk = photo_pk_queue.get()
        for format_name in ("avif", "webp"):
            if format_name == "avif" and not AVIF_SUPPORTED:
                continue
            for size in (150, 800):
                _get_thumbnail_path(photo_pk, format_name, size, size)
        photo_pk_queue.task_done()


class Command(management.BaseCommand):
    help = "Prerender thumbnails for all photos."

    def handle(self, *args: Any, **kwargs: Any) -> None:
        from tumpara.photos.models import Photo

        queryset = Photo.objects.filter(~models.Q(main_path="")).values_list("pk")
        total_count = len(queryset)

        thread_count = check_thread_count()
        context = multiprocessing.get_context("spawn")
        photo_pk_queue: multiprocessing.JoinableQueue[int] = context.JoinableQueue(
            maxsize=2 * thread_count
        )

        connection.close()

        _logger.info(
            f"Starting photo thumbnail generation with {thread_count} thread(s)."
        )

        for _ in range(thread_count):
            context.Process(
                target=worker,
                args=(photo_pk_queue,),
                daemon=True,
            ).start()

        for index, (photo_pk,) in enumerate(queryset):
            photo_pk_queue.put(photo_pk)
            if index % 100 == 99 and index > 200:
                _logger.info(
                    f"At least {index - 200 + 1} of {total_count} thumbnails checked "
                    f"so far."
                )
        photo_pk_queue.join()

        _logger.info(f"Checked {total_count} thumbnails.")
