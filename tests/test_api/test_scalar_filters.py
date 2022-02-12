import functools

import hypothesis
from django.db.models import Q

from tumpara.api.filtering import FloatFilter, IntFilter, StringFilter
from tumpara.testing import strategies as st

# Note: these tests basically only test if the Q object we get when evaluating the
# filters is what we expect. Since databases behave somewhat different in terms of
# string case-sensitivity, we need a framework that incorporates the anomalies somehow
# before testing on an actual database first. Most notably this is the case for SQLite,
# see here:
#   https://docs.djangoproject.com/en/4.0/ref/databases/#sqlite-string-matching
# For MySQL, it also seems to be dependant on database settings:
#   https://docs.djangoproject.com/en/4.0/ref/models/querysets/#exact


filter_string = functools.partial(
    StringFilter,
    include=None,
    exclude=None,
    contains=None,
    does_not_contain=None,
    starts_with=None,
    does_not_start_with=None,
    ends_with=None,
    does_not_end_with=None,
)
filter_int = functools.partial(
    IntFilter,
    include=None,
    exclude=None,
    minimum=None,
    maximum=None,
)
filter_float = functools.partial(
    FloatFilter,
    include=None,
    exclude=None,
    minimum=None,
    maximum=None,
)


def test_string_equality() -> None:
    assert filter_string(include=["hi"]).build_query("foo") == Q(foo__exact="hi")
    assert filter_string(exclude=["hi"]).build_query("foo") == ~Q(foo__exact="hi")
    assert filter_string(include=["hi", "hu"]).build_query("foo__bar") == Q(
        foo__bar__in=["hi", "hu"]
    )
    assert filter_string(exclude=["hi", "hu"]).build_query("foo__bar") == ~Q(
        foo__bar__in=["hi", "hu"]
    )


def test_string_contains() -> None:
    assert filter_string(contains="hi").build_query("foo") == Q(foo__icontains="hi")
    assert filter_string(contains="hi", case_sensitive=True).build_query("foo") == Q(
        foo__contains="hi"
    )
    assert filter_string(does_not_contain="hello").build_query("foo__bar") == ~Q(
        foo__bar__icontains="hello"
    )
    assert filter_string(does_not_contain="hello", case_sensitive=True).build_query(
        "foo__bar"
    ) == ~Q(foo__bar__contains="hello")


def test_string_starts() -> None:
    assert filter_string(starts_with="hi").build_query("foo") == Q(
        foo__istartswith="hi"
    )
    assert filter_string(starts_with="hi", case_sensitive=True).build_query("foo") == Q(
        foo__startswith="hi"
    )
    assert filter_string(does_not_start_with="hello").build_query("foo__bar") == ~Q(
        foo__bar__istartswith="hello"
    )
    assert filter_string(does_not_start_with="hello", case_sensitive=True).build_query(
        "foo__bar"
    ) == ~Q(foo__bar__startswith="hello")


def test_string_ends() -> None:
    assert filter_string(ends_with="hi").build_query("foo") == Q(foo__iendswith="hi")
    assert filter_string(ends_with="hi", case_sensitive=True).build_query("foo") == Q(
        foo__endswith="hi"
    )
    assert filter_string(does_not_end_with="hello").build_query("foo__bar") == ~Q(
        foo__bar__iendswith="hello"
    )
    assert filter_string(does_not_end_with="hello", case_sensitive=True).build_query(
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
    assert filter_string(
        contains=value_a,
        starts_with=value_b,
        ends_with=value_c,
    ).build_query(field_name) == Q(
        (f"{field_name}__icontains", value_a),
        (f"{field_name}__istartswith", value_b),
        (f"{field_name}__iendswith", value_c),
    )
    assert filter_string(
        does_not_contain=value_a,
        starts_with=value_b,
        does_not_end_with=value_c,
    ).build_query(field_name) == Q(
        ~Q((f"{field_name}__icontains", value_a)),
        (f"{field_name}__istartswith", value_b),
        ~Q((f"{field_name}__iendswith", value_c)),
    )
    assert filter_string(
        include=[value_a, value_b],
        does_not_start_with=value_c,
        case_sensitive=True,
    ).build_query(field_name) == Q(
        (f"{field_name}__in", [value_a, value_b]),
        ~Q((f"{field_name}__startswith", value_c)),
    )


def test_number_equality() -> None:
    assert filter_int(include=[9]).build_query("foo") == Q(foo__exact=9)
    assert filter_int(exclude=[-4]).build_query("foo") == ~Q(foo__exact=-4)
    assert filter_float(include=[8.9]).build_query("foo") == Q(foo__exact=8.9)
    assert filter_float(exclude=[-2.4]).build_query("foo") == ~Q(foo__exact=-2.4)

    assert filter_int(include=[2, -5, 17]).build_query("foo__bar") == Q(
        foo__bar__in=[2, -5, 17]
    )
    assert filter_int(exclude=[1, 17, -4]).build_query("foo__bar") == ~Q(
        foo__bar__in=[1, 17, -4]
    )
    assert filter_float(include=[4, -3.4, 0.999]).build_query("foo__bar") == Q(
        foo__bar__in=[4, -3.4, 0.999]
    )
    assert filter_float(exclude=[1.2, -43, 0.0]).build_query("foo__bar") == ~Q(
        foo__bar__in=[1.2, -43, 0.0]
    )


def test_number_single_bound() -> None:
    assert filter_int(minimum=4).build_query("foo") == Q(foo__gte=4)
    assert filter_int(minimum=-7, inclusive_minimum=False).build_query("foo__bar") == Q(
        foo__bar__gt=-7
    )
    assert filter_float(minimum=2.3).build_query("foo") == Q(foo__gte=2.3)
    assert filter_float(minimum=-9.2, inclusive_minimum=False).build_query(
        "foo__bar"
    ) == Q(foo__bar__gt=-9.2)

    assert filter_int(maximum=2).build_query("foo") == Q(foo__lte=2)
    assert filter_int(maximum=-5, inclusive_maximum=False).build_query("foo__bar") == Q(
        foo__bar__lt=-5
    )
    assert filter_float(maximum=6.5).build_query("foo") == Q(foo__lte=6.5)
    assert filter_float(maximum=-8.1, inclusive_maximum=False).build_query(
        "foo__bar"
    ) == Q(foo__bar__lt=-8.1)


def test_number_both_bounds() -> None:
    """The ``__range`` lookup gets used when both bounds are marked inclusive.
    Otherwise less-than and greater-than are used in combination."""
    assert filter_int(minimum=2, maximum=6).build_query("foo") == Q(foo__range=(2, 6))
    assert filter_int(minimum=1, inclusive_minimum=False, maximum=7).build_query(
        "foo__bar"
    ) == Q(foo__bar__gt=1, foo__bar__lte=7)
    assert filter_int(minimum=0, maximum=2, inclusive_maximum=False).build_query(
        "bar__foo"
    ) == Q(bar__foo__gte=0, bar__foo__lt=2)
    assert filter_int(
        minimum=-4, inclusive_minimum=False, maximum=4, inclusive_maximum=False
    ).build_query("bar") == Q(bar__gt=-4, bar__lt=4)

    assert filter_float(minimum=1.2, maximum=4.5).build_query("foo") == Q(
        foo__range=(1.2, 4.5)
    )
    assert filter_float(
        minimum=2.22, inclusive_minimum=False, maximum=2.23
    ).build_query("foo__bar") == Q(foo__bar__gt=2.22, foo__bar__lte=2.23)
    assert filter_float(minimum=0, maximum=2.0, inclusive_maximum=False).build_query(
        "bar__foo"
    ) == Q(bar__foo__gte=0, bar__foo__lt=2.0)
    assert filter_float(
        minimum=-3.3, inclusive_minimum=False, maximum=3.3, inclusive_maximum=False
    ).build_query("bar") == Q(bar__gt=-3.3, bar__lt=3.3)
