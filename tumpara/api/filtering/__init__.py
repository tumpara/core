from typing import Protocol

from django.db import models

from .scalars import FloatFilter, IntFilter, StringFilter

__all__ = [
    "FloatFilter",
    "GenericFilter",
    "IntFilter",
    "StringFilter",
]


class GenericFilter(Protocol):
    def build_query(self, field_name: str) -> models.Q:
        ...
