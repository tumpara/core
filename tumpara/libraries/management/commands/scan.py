import logging
from typing import Any

from django.core import management

from tumpara.libraries.models import Library

_logger = logging.getLogger(__name__)


class Command(management.BaseCommand):
    help = "Run a full scan on all libraries."

    def handle(self, *args: Any, **kwargs: Any) -> None:
        library_count = Library.objects.count()
        if library_count == 0:
            _logger.warning("Could not start scan because no libraries exist.")
            return
        elif library_count == 1:
            _logger.info(f"Starting consecutive scan of {library_count} library...")
        else:
            _logger.info(f"Starting consecutive scan of {library_count} libraries...")

        for library in Library.objects.filter(pk=2):
            library.scan()
