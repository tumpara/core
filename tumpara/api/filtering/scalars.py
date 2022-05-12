import abc
import datetime
from typing import SupportsFloat  # noqa: F401  # pylint: disable=unused-import
from typing import Any, Generic, Optional, TypeVar

import strawberry
from django.db import models
from django.db.models import functions

from ..utils import InfoType

_T = TypeVar("_T")
_N = TypeVar("_N", bound="SupportsFloat")


@strawberry.input
class ScalarFilter(Generic[_T], abc.ABC):
    include: Optional[list[_T]] = None
    exclude: Optional[list[_T]] = None

    @abc.abstractmethod
    def build_query(self, info: InfoType, field_name: str) -> models.Q:
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


@strawberry.input(description="Filtering options for string fields.")
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

    def build_query(self, info: InfoType, field_name: str) -> models.Q:
        query = super().build_query(info, field_name)
        prefix = f"{field_name}__{'' if self.case_sensitive else 'i'}"

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

    def build_query(self, info: InfoType, field_name: str) -> models.Q:
        query = super().build_query(info, field_name)

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


@strawberry.input(description="Filtering options for integer fields.")
class IntFilter(NumberFilter[int]):
    include: Optional[list[int]] = None
    exclude: Optional[list[int]] = None
    minimum: Optional[int] = None
    maximum: Optional[int] = None


@strawberry.input(description="Filtering options for float fields.")
class FloatFilter(NumberFilter[float]):
    include: Optional[list[float]] = None
    exclude: Optional[list[float]] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None


@strawberry.input(description="Filtering options for date fields.")
class DateFilter:
    before: Optional[datetime.datetime] = strawberry.field(
        default=None,
        description="Match values before this date.",
    )
    after: Optional[datetime.datetime] = strawberry.field(
        default=None,
        description="Match values after this date.",
    )
    inclusive: bool = strawberry.field(
        default=False,
        description="Set to `true` to make the `before` and `after` options "
        "inclusive.",
    )
    year: Optional[IntFilter] = strawberry.field(
        default=None,
        description="Filter based on the year.",
    )
    month: Optional[IntFilter] = strawberry.field(
        default=None,
        description="Filter based on the month (values between 1 and 12).",
    )
    day: Optional[IntFilter] = strawberry.field(
        default=None,
        description="Filter based on the day of the month (values between 1 and 31).",
    )
    week_day: Optional[IntFilter] = strawberry.field(
        default=None,
        description="Filter based on the day of the week (values between 1 and 7, "
        "counting from Sunday to Saturday).",
    )

    def build_query(
        self, info: InfoType, field_name: str
    ) -> tuple[models.Q, dict[str, models.Expression]]:
        query = models.Q()
        aliases = dict[str, models.Expression]()

        inclusivity_suffix = "e" if self.inclusive else ""
        if self.before is not None:
            query &= models.Q((f"{field_name}__lt{inclusivity_suffix}", self.before))
        if self.after is not None:
            query &= models.Q((f"{field_name}__gt{inclusivity_suffix}", self.after))

        if self.year is not None:
            alias = f"_{field_name}_year"
            aliases[alias] = functions.ExtractYear(field_name)
            query &= self.year.build_query(info, alias)
        if self.month is not None:
            alias = f"_{field_name}_month"
            aliases[alias] = functions.ExtractMonth(field_name)
            query &= self.month.build_query(info, alias)
        if self.day is not None:
            alias = f"_{field_name}_day"
            aliases[alias] = functions.ExtractDay(field_name)
            query &= self.day.build_query(info, alias)
        if self.week_day is not None:
            alias = f"_{field_name}_week_day"
            aliases[alias] = functions.ExtractWeekDay(field_name)
            query &= self.week_day.build_query(info, alias)

        return query, aliases


@strawberry.input(description="Filtering options for datetime fields.")
class DateTimeFilter(DateFilter):
    hour: Optional[IntFilter] = strawberry.field(
        default=None,
        description="Filter based on the hour (values between 0 and 23).",
    )

    def build_query(
        self, info: InfoType, field_name: str
    ) -> tuple[models.Q, dict[str, models.Expression]]:
        query, aliases = super().build_query(info, field_name)

        if self.hour is not None:
            alias = f"_{field_name}_hour"
            aliases[alias] = functions.ExtractHour(field_name)
            query &= self.hour.build_query(info, alias)

        return query, aliases


@strawberry.input(description="Filtering options for time fields.")
class TimeFilter:
    before_time: Optional[datetime.time] = strawberry.field(
        default=None,
        description="Match values earlier than this time.",
    )
    after_time: Optional[datetime.time] = strawberry.field(
        default=None,
        description="Match values later than this time.",
    )
    inclusive: bool = strawberry.field(
        default=False,
        description="Set to `true` to make the `before_time` and `after_time` options "
        "inclusive.",
    )

    def build_query(self, info: InfoType, field_name: str) -> models.Q:
        query = models.Q()

        inclusivity_suffix = "e" if self.inclusive else ""
        if self.before_time is not None:
            query &= models.Q(
                (f"{field_name}__lt{inclusivity_suffix}", self.before_time)
            )
        if self.after_time is not None:
            query &= models.Q(
                (f"{field_name}__gt{inclusivity_suffix}", self.after_time)
            )

        return query
