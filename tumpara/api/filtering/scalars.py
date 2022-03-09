import abc
from typing import SupportsFloat  # noqa: F401, used in the _N type variable
from typing import Any, Generic, Optional, TypeVar

import strawberry
from django.db import models

_T = TypeVar("_T")
_N = TypeVar("_N", bound="SupportsFloat")


@strawberry.input
class ScalarFilter(Generic[_T], abc.ABC):
    include: Optional[list[_T]] = None
    exclude: Optional[list[_T]] = None

    @abc.abstractmethod
    def build_query(self, field_name: str) -> models.Q:
        """Build a Django ``Q`` object for this filter.

        :param field_name: Name of the field or related field lookup the filter should
            be applied on. For example, if you want to query a name field, this should
            be set to ``name``. If you want to query the name field of a related
            collection object, this should be ``collections__name``.
        """
        query = models.Q()

        if self.include is not None:
            if len(self.include) == 1:
                query &= models.Q((f"{field_name}__exact", self.include[0]))
            elif len(self.include) > 1:
                query &= models.Q((f"{field_name}__in", self.include))
        if self.exclude is not None:
            if len(self.exclude) == 1:
                query &= ~models.Q((f"{field_name}__exact", self.exclude[0]))
            elif len(self.exclude) > 1:
                query &= ~models.Q((f"{field_name}__in", self.exclude))

        return query


@strawberry.input
class StringFilter(ScalarFilter[str]):
    include: Optional[list[str]] = strawberry.field(
        default=None,
        description="Explicit list of possible strings. Only objects with one of these "
        "set will be matched.",
    )
    exclude: Optional[list[str]] = strawberry.field(
        default=None,
        description="Explicit list of excluded strings. Objects with one of these set "
        "will not be returned, even if other filters match.",
    )
    contains: Optional[str] = strawberry.field(
        default=None,
        description="Match field values that contain the provided string.",
    )
    does_not_contain: Optional[str] = strawberry.field(
        default=None,
        description="Objects where the field value contains the provided string will "
        "not be returned, even if other filters match.",
    )
    starts_with: Optional[str] = strawberry.field(
        default=None,
        description="Match field values that start with the provided string.",
    )
    does_not_start_with: Optional[str] = strawberry.field(
        default=None,
        description="Objects where the field value starts with the provided string "
        "will not be returned, even if other filters match.",
    )
    ends_with: Optional[str] = strawberry.field(
        default=None,
        description="Match field values that end with the provided string.",
    )
    does_not_end_with: Optional[str] = strawberry.field(
        default=None,
        description="Objects where the field value ends with the provided string "
        "will not be returned, even if other filters match.",
    )
    case_sensitive: bool = strawberry.field(
        default=False,
        description="By default, all filters are case insensitive. Set this to `true` "
        "filter for exact matches. Note that this setting is ignored for the `include` "
        "and `exclude` options. Also note that SQLite doesn't support case-sensitive "
        "filtering.",
    )

    def build_query(self, field_name: str) -> models.Q:
        query = super().build_query(field_name)
        case_prefix = "" if self.case_sensitive else "i"
        prefix = field_name + "__" + case_prefix

        if self.contains is not None:
            query &= models.Q((f"{prefix}contains", self.contains))
        if self.does_not_contain is not None:
            query &= ~models.Q((f"{prefix}contains", self.does_not_contain))

        if self.starts_with is not None:
            query &= models.Q((f"{prefix}startswith", self.starts_with))
        if self.does_not_start_with is not None:
            query &= ~models.Q((f"{prefix}startswith", self.does_not_start_with))

        if self.ends_with is not None:
            query &= models.Q((f"{prefix}endswith", self.ends_with))
        if self.does_not_end_with is not None:
            query &= ~models.Q((f"{prefix}endswith", self.does_not_end_with))

        return query


@strawberry.input
class NumberFilter(Generic[_N], ScalarFilter[_N]):
    include: Optional[list[_N]] = None
    exclude: Optional[list[_N]] = None
    minimum: Optional[_N] = None
    maximum: Optional[_N] = None
    inclusive_minimum: bool = strawberry.field(
        default=True,
        description="By default, the `minimum` filter is inclusive. Set this to "
        "`false` to make it exclusive (turn the *greater-than-equals* into a "
        "*greater-than*).",
    )
    inclusive_maximum: bool = strawberry.field(
        default=True,
        description="By default, the `maximum` filter is inclusive. Set this to "
        "`false` to make it exclusive (turn the *less-than-equals* into a "
        "*less-than*).",
    )

    def __init_subclass__(cls, **kwargs: Any):
        # Initialize generic fields. See the comment in __init_subclass__ of
        # tumpara.api.relay.connection.Connection for more details on why this is done.
        cls.include = strawberry.field(
            default=None,
            description="Explicit list of possible values. Only objects with one of "
            "these set will be matched.",
        )
        cls.exclude = strawberry.field(
            default=None,
            description="Explicit list of excluded values. Objects with one of these "
            "set will not be returned, even if other filters match.",
        )
        cls.minimum = strawberry.field(
            default=None,
            description="Match objects with field values of at least the one "
            "specified.",
        )
        cls.maximum = strawberry.field(
            default=None,
            description="Match objects with field values of at most the one specified.",
        )

        super().__init_subclass__(**kwargs)

    def build_query(self, field_name: str) -> models.Q:
        query = super().build_query(field_name)

        if (
            self.inclusive_minimum
            and self.inclusive_maximum
            and self.minimum is not None
            and self.maximum is not None
        ):
            query &= models.Q((f"{field_name}__range", (self.minimum, self.maximum)))
        else:
            if self.minimum is not None:
                equals_suffix = "e" if self.inclusive_minimum else ""
                query &= models.Q((f"{field_name}__gt{equals_suffix}", self.minimum))

            if self.maximum is not None:
                equals_suffix = "e" if self.inclusive_maximum else ""
                query &= models.Q((f"{field_name}__lt{equals_suffix}", self.maximum))

        return query


@strawberry.input
class IntFilter(NumberFilter[int]):
    include: Optional[list[int]] = None
    exclude: Optional[list[int]] = None
    minimum: Optional[int] = None
    maximum: Optional[int] = None


@strawberry.input
class FloatFilter(NumberFilter[float]):
    include: Optional[list[float]] = None
    exclude: Optional[list[float]] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
