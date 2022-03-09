from typing import Any, Optional

import hypothesis
import pytest

from tumpara.api import relay
from tumpara.testing import strategies as st


@st.composite
def connection_test_data(
    draw: st.DrawFn,
) -> tuple[int, Optional[int], Optional[int], Optional[int], Optional[int]]:
    dataset_size = draw(st.integers(20, 50))
    after = draw(
        st.one_of(st.none(), st.integers(int(-dataset_size * 0.5), dataset_size * 2))
    )
    before = draw(
        st.one_of(st.none(), st.integers(-dataset_size, int(dataset_size * 1.5)))
    )
    first = draw(st.one_of(st.none(), st.integers(0, dataset_size * 2)))
    last = draw(st.one_of(st.none(), st.integers(0, dataset_size * 2)))
    return dataset_size, after, before, first, last


def create_connection(
    dataset: list[int],
    after: Optional[int | str] = None,
    before: Optional[int | str] = None,
    first: Optional[int] = None,
    last: Optional[int] = None,
) -> relay.Connection[Any]:
    return relay.Connection.from_sequence(
        dataset,
        after=relay.encode_key("Connection", after)
        if isinstance(after, int)
        else after,
        before=relay.encode_key("Connection", before)
        if isinstance(before, int)
        else before,
        first=first,
        last=last,
    )


@hypothesis.given(connection_test_data())
@hypothesis.example((20, None, None, None, 19))
def test_connection_building_bounds(
    data: tuple[int, Optional[int], Optional[int], Optional[int], Optional[int]]
) -> None:
    """Building connections from iterables returns the correct number of edges, with
    the correct bounds set in PageInfo."""
    dataset_size, after, before, first, last = data
    dataset = list(range(0, dataset_size))
    connection = create_connection(dataset, after, before, first, last)

    assert connection.total_count == len(dataset)

    if first is not None:
        assert len(connection.edges) <= first
    if last is not None:
        assert len(connection.edges) <= last
    for edge in connection.edges:
        if edge is None:
            continue
        if before is not None:
            assert edge.node < before
        if after is not None:
            assert edge.node > after

    if len(connection.edges) > 0:
        # While we could argue that this assumption is technically a valid
        # interpretation of the spec, it does lead to some edge cases that are ignored,
        # like:
        #   (first=2,last=5) on the dataset [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        # Here, both forward and backward pagination may technically have adjacent pages
        # with more data (and the corresponding has_..._page values will be set). But,
        # since forward pagination is processed first, the output will be this:
        #   [0, 1]
        # Therefore we end up with a result where pagination is clearly only possible
        # in the forward direction, but - according to the Relay space - both flags in
        # PageInfo will be set. There isn't much we can do here to be clever other than
        # avoid this case (which really is an edge case that nobody should ever be
        # using) and focus on testing the important parts.
        hypothesis.assume(first is None or last is None)

        if first is not None:
            # When paginating forwards, has_next_page should be set correctly.
            before_or_integer = (
                min(before, dataset_size) if before is not None else dataset_size
            )
            assert connection.edges[-1] is not None
            assert connection.page_info.has_next_page is (
                connection.edges[-1].node < before_or_integer - 1
            )
        else:
            # When not paginating forwards, no hint about the next page should be given.
            assert not connection.page_info.has_next_page

        if last is not None:
            # When paginating backwards, has_previous_page should be set correctly.
            after_integer = max(after, -1) if after is not None else -1
            assert connection.edges[0] is not None
            assert connection.page_info.has_previous_page is (
                connection.edges[0].node > after_integer + 1
            )
        else:
            # When not paginating backwards, no hint about the previous page should
            # be given.
            assert not connection.page_info.has_previous_page

        first_or_inf = first if first is not None else float("inf")
        last_or_inf = last if last is not None else float("inf")

        if connection.page_info.has_next_page:
            assert connection.edges[-1] is not None
            assert connection.edges[-1].node < dataset_size - 1
            if first is not None:
                assert len(connection.edges) == min(first, last_or_inf)

        if connection.page_info.has_previous_page:
            assert connection.edges[0] is not None
            assert connection.edges[0].node > 0
            if last is not None:
                assert len(connection.edges) == min(last, first_or_inf)


@hypothesis.given(st.integers(0, 100), st.integers(1, 9))
@hypothesis.example(50, 6)
def test_connection_building_pagination(starting_point: int, page_size: int) -> None:
    """Paginating through a dataset works as expected."""
    dataset = list(range(0, 101))
    results = list[Optional[int]]()

    # Paginate forwards from the starting point (inclusive):
    cursor: Optional[str | int] = starting_point - 1
    while cursor is not None:
        connection = create_connection(dataset, after=cursor, first=page_size)
        results.extend(
            edge.node if edge is not None else None for edge in connection.edges
        )
        cursor = connection.page_info.end_cursor
        if not connection.page_info.has_next_page:
            break

    # Paginate backwards from the starting point (exclusive):
    cursor = starting_point
    while cursor is not None:
        connection = create_connection(dataset, before=cursor, last=page_size)
        results = [
            *[edge.node if edge is not None else None for edge in connection.edges],
            *results,
        ]
        cursor = connection.page_info.start_cursor
        if not connection.page_info.has_previous_page:
            break

    assert results == dataset


def test_connection_building_errors() -> None:
    with pytest.raises(ValueError):
        create_connection([], after="thisisnotbase64")
    with pytest.raises(ValueError):
        create_connection([], after=relay.encode_key("wrong_key", 15))
    with pytest.raises(ValueError):
        create_connection([], before="thisisnotbase64")
    with pytest.raises(ValueError):
        create_connection([], before=relay.encode_key("wrong_key", 15))
    with pytest.raises(ValueError):
        create_connection([], first=-3)
    with pytest.raises(ValueError):
        create_connection([], last=-5)
