from typing import Protocol

from django.db import models


class GenericFilter(Protocol):
    def build_query(self, field_name: str) -> models.Q:
        ...
