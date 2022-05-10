import datetime

import hypothesis
from django.db.models import Q

from tumpara.api import (
    DateFilter,
    DateTimeFilter,
    FloatFilter,
    IntFilter,
    StringFilter,
    TimeFilter,
)
from tumpara.testing import strategies as st

# Note: these tests basically only test if the Q object we get when evaluating the
# filters is what we expect. Since databases behave somewhat different in terms of
# string case-sensitivity, we need a framework that incorporates the anomalies somehow
# before testing on an actual database first. Most notably this is the case for SQLite,
# see here:
#   https://docs.djangoproject.com/en/4.0/ref/databases/#sqlite-string-matching
# For MySQL, it also seems to be dependent on database settings:
#   https://docs.djangoproject.com/en/4.0/ref/models/querysets/#exact


def test_string_equality() -> None:
    assert StringFilter(include=["hi"]).build_query("foo") == Q(foo__exact="hi")
    assert StringFilter(exclude=["hi"]).build_query("foo") == ~Q(foo__exact="hi")
    assert StringFilter(include=["hi", "hu"]).build_query("foo__bar") == Q(
        foo__bar__in=["hi", "hu"]
    )
    assert StringFilter(exclude=["hi", "hu"]).build_query("foo__bar") == ~Q(
        foo__bar__in=["hi", "hu"]
    )


def test_string_contains() -> None:
    assert StringFilter(contains="hi").build_query("foo") == Q(foo__icontains="hi")
    assert StringFilter(contains="hi", case_sensitive=True).build_query("foo") == Q(
        foo__contains="hi"
    )
    assert StringFilter(does_not_contain="hello").build_query("foo__bar") == ~Q(
        foo__bar__icontains="hello"
    )
    assert StringFilter(does_not_contain="hello", case_sensitive=True).build_query(
        "foo__bar"
    ) == ~Q(foo__bar__contains="hello")


def test_string_starts() -> None:
    assert StringFilter(starts_with="hi").build_query("foo") == Q(foo__istartswith="hi")
    assert StringFilter(starts_with="hi", case_sensitive=True).build_query("foo") == Q(
        foo__startswith="hi"
    )
    assert StringFilter(does_not_start_with="hello").build_query("foo__bar") == ~Q(
        foo__bar__istartswith="hello"
    )
    assert StringFilter(does_not_start_with="hello", case_sensitive=True).build_query(
        "foo__bar"
    ) == ~Q(foo__bar__startswith="hello")


def test_string_ends() -> None:
    assert StringFilter(ends_with="hi").build_query("foo") == Q(foo__iendswith="hi")
    assert StringFilter(ends_with="hi", case_sensitive=True).build_query("foo") == Q(
        foo__endswith="hi"
    )
    assert StringFilter(does_not_end_with="hello").build_query("foo__bar") == ~Q(
        foo__bar__iendswith="hello"
    )
    assert StringFilter(does_not_end_with="hello", case_sensitive=True).build_query(
        "foo__bar"
    ) == ~Q(foo__bar__endswith="hello")


@hypothesis.given(
    st.field_names(), st.text(min_size=1), st.text(min_size=1), st.text(min_size=1)
)
def test_string_complex(
    field_name: str, value_a: str, value_b: str, value_c: str
) -> None:
    # The order of stuff in the expected Q objects here is important, because it needs
    # to match what we have in the implementation otherwise the comparison doesn't work.
    assert StringFilter(
        contains=value_a,
        starts_with=value_b,
        ends_with=value_c,
    ).build_query(field_name) == Q(
        (f"{field_name}__icontains", value_a),
        (f"{field_name}__istartswith", value_b),
        (f"{field_name}__iendswith", value_c),
    )
    assert StringFilter(
        does_not_contain=value_a,
        starts_with=value_b,
        does_not_end_with=value_c,
    ).build_query(field_name) == Q(
        ~Q((f"{field_name}__icontains", value_a)),
        (f"{field_name}__istartswith", value_b),
        ~Q((f"{field_name}__iendswith", value_c)),
    )
    assert StringFilter(
        include=[value_a, value_b],
        does_not_start_with=value_c,
        case_sensitive=True,
    ).build_query(field_name) == Q(
        (f"{field_name}__in", [value_a, value_b]),
        ~Q((f"{field_name}__startswith", value_c)),
    )


def test_number_equality() -> None:
    assert IntFilter(include=[9]).build_query("foo") == Q(foo__exact=9)
    assert IntFilter(exclude=[-4]).build_query("foo") == ~Q(foo__exact=-4)
    assert FloatFilter(include=[8.9]).build_query("foo") == Q(foo__exact=8.9)
    assert FloatFilter(exclude=[-2.4]).build_query("foo") == ~Q(foo__exact=-2.4)

    assert IntFilter(include=[2, -5, 17]).build_query("foo__bar") == Q(
        foo__bar__in=[2, -5, 17]
    )
    assert IntFilter(exclude=[1, 17, -4]).build_query("foo__bar") == ~Q(
        foo__bar__in=[1, 17, -4]
    )
    assert FloatFilter(include=[4, -3.4, 0.999]).build_query("foo__bar") == Q(
        foo__bar__in=[4, -3.4, 0.999]
    )
    assert FloatFilter(exclude=[1.2, -43, 0.0]).build_query("foo__bar") == ~Q(
        foo__bar__in=[1.2, -43, 0.0]
    )


def test_number_single_bound() -> None:
    assert IntFilter(minimum=4).build_query("foo") == Q(foo__gte=4)
    assert IntFilter(minimum=-7, inclusive_minimum=False).build_query("foo__bar") == Q(
        foo__bar__gt=-7
    )
    assert FloatFilter(minimum=2.3).build_query("foo") == Q(foo__gte=2.3)
    assert FloatFilter(minimum=-9.2, inclusive_minimum=False).build_query(
        "foo__bar"
    ) == Q(foo__bar__gt=-9.2)

    assert IntFilter(maximum=2).build_query("foo") == Q(foo__lte=2)
    assert IntFilter(maximum=-5, inclusive_maximum=False).build_query("foo__bar") == Q(
        foo__bar__lt=-5
    )
    assert FloatFilter(maximum=6.5).build_query("foo") == Q(foo__lte=6.5)
    assert FloatFilter(maximum=-8.1, inclusive_maximum=False).build_query(
        "foo__bar"
    ) == Q(foo__bar__lt=-8.1)


def test_number_both_bounds() -> None:
    """The ``__range`` lookup gets used when both bounds are marked inclusive.
    Otherwise less-than and greater-than are used in combination."""
    assert IntFilter(minimum=2, maximum=6).build_query("foo") == Q(foo__range=(2, 6))
    assert IntFilter(minimum=1, inclusive_minimum=False, maximum=7).build_query(
        "foo__bar"
    ) == Q(foo__bar__gt=1, foo__bar__lte=7)
    assert IntFilter(minimum=0, maximum=2, inclusive_maximum=False).build_query(
        "bar__foo"
    ) == Q(bar__foo__gte=0, bar__foo__lt=2)
    assert IntFilter(
        minimum=-4, inclusive_minimum=False, maximum=4, inclusive_maximum=False
    ).build_query("bar") == Q(bar__gt=-4, bar__lt=4)

    assert FloatFilter(minimum=1.2, maximum=4.5).build_query("foo") == Q(
        foo__range=(1.2, 4.5)
    )
    assert FloatFilter(minimum=2.22, inclusive_minimum=False, maximum=2.23).build_query(
        "foo__bar"
    ) == Q(foo__bar__gt=2.22, foo__bar__lte=2.23)
    assert FloatFilter(minimum=0, maximum=2.0, inclusive_maximum=False).build_query(
        "bar__foo"
    ) == Q(bar__foo__gte=0, bar__foo__lt=2.0)
    assert FloatFilter(
        minimum=-3.3, inclusive_minimum=False, maximum=3.3, inclusive_maximum=False
    ).build_query("bar") == Q(bar__gt=-3.3, bar__lt=3.3)


def test_time_bounds() -> None:
    assert TimeFilter(before_time=datetime.time(hour=12)).build_query("foo") == Q(
        foo__lt=datetime.time(hour=12)
    )
    assert TimeFilter(before_time=datetime.time(hour=6), inclusive=True).build_query(
        "bar"
    ) == Q(bar__lte=datetime.time(hour=6))
    assert TimeFilter(after_time=datetime.time(hour=14)).build_query("foo") == Q(
        foo__gt=datetime.time(hour=14)
    )
    assert TimeFilter(after_time=datetime.time(hour=20), inclusive=True).build_query(
        "bar"
    ) == Q(bar__gte=datetime.time(hour=20))


def test_date_bounds() -> None:
    date = datetime.datetime(year=2000, month=1, day=1)

    assert DateFilter(before=date).build_query("foo") == (Q(foo__lt=date), {})
    assert DateFilter(before=date, inclusive=True).build_query("bar") == (
        Q(bar__lte=date),
        {},
    )
    assert DateFilter(after=date).build_query("foo") == (Q(foo__gt=date), {})
    assert DateFilter(after=date, inclusive=True).build_query("bar") == (
        Q(bar__gte=date),
        {},
    )


def test_date_parts() -> None:
    number_filter = IntFilter(exclude=[16, 19], minimum=15, maximum=22)

    query, aliases = DateFilter(year=number_filter).build_query("foo")
    assert query == number_filter.build_query("_foo_year")
    assert "_foo_year" in aliases

    query, aliases = DateFilter(month=number_filter).build_query("foo")
    assert query == number_filter.build_query("_foo_month")
    assert "_foo_month" in aliases

    query, aliases = DateFilter(day=number_filter).build_query("foo")
    assert query == number_filter.build_query("_foo_day")
    assert "_foo_day" in aliases

    query, aliases = DateFilter(week_day=number_filter).build_query("foo")
    assert query == number_filter.build_query("_foo_week_day")
    assert "_foo_week_day" in aliases

    query, aliases = DateTimeFilter(hour=number_filter).build_query("foo")
    assert query == number_filter.build_query("_foo_hour")
    assert "_foo_hour" in aliases
