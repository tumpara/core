from typing import Any

import hypothesis
import pytest
from django.utils import timezone

from tumpara import api
from tumpara.accounts.models import User
from tumpara.libraries.models import Library, Note, Visibility
from tumpara.testing import strategies as st

from .test_notes_api import user  # noqa: F401

ASSET_PAGINATION_QUERY = """
    query AssetPagination($after: String, $before: String, $first: Int, $last: Int) {
      assets(after: $after, before: $before, first: $first, last: $last) {
        pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
        nodes {
          __typename
          ... on Note { content }
        }
      }
    }
"""


def create_library(user: User) -> Library:
    library = Library.objects.create(source="testing:///", context="test_storage")
    library.add_membership(user, owner=True)
    return library


@pytest.fixture
def library(user: User) -> Library:
    return create_library(user)


@pytest.fixture
def notes(library: Library) -> list[Note]:
    return [
        Note.objects.create(  # 0
            library=library,
            content="First note.",
            media_timestamp=timezone.datetime(2017, 1, 4, 14, 15),
        ),
        Note.objects.create(  # 1
            library=library,
            content="Second note.",
            media_timestamp=timezone.datetime(2020, 1, 4, 17, 12),
            visibility=Visibility.PUBLIC,
        ),
        Note.objects.create(  # 2
            library=library,
            content="Third note.",
            media_timestamp=timezone.datetime(2022, 1, 2, 3, 30),
            visibility=Visibility.INTERNAL,
        ),
        Note.objects.create(  # 3
            library=library,
            content="Fourth note.",
            media_timestamp=timezone.datetime(2022, 1, 4, 3, 30),
            visibility=Visibility.MEMBERS,
        ),
        Note.objects.create(  # 4
            library=library,
            content="Fifth note.",
            media_timestamp=timezone.datetime(2022, 1, 4, 3, 30),
            visibility=Visibility.OWNERS,
        ),
        Note.objects.create(  # 5
            library=library,
            content="Sixth note.",
            media_timestamp=timezone.datetime(2022, 1, 4, 3, 30),
            visibility=Visibility.PUBLIC,
        ),
        Note.objects.create(  # 6
            library=library,
            content="Seventh note.",
            media_timestamp=timezone.datetime(2022, 1, 5, 3, 30),
            visibility=Visibility.INTERNAL,
        ),
        Note.objects.create(  # 7
            library=library,
            content="Eighth note.",
            media_timestamp=timezone.datetime(2022, 2, 1, 4, 24),
            visibility=Visibility.MEMBERS,
        ),
        Note.objects.create(  # 8
            library=library,
            content="Ninth note.",
            media_timestamp=timezone.datetime(2022, 3, 1, 15, 28),
            visibility=Visibility.OWNERS,
        ),
        Note.objects.create(  # 9
            library=library,
            content="Tenth note.",
            media_timestamp=timezone.datetime(2023, 4, 5, 11, 12),
        ),
    ]


@pytest.mark.django_db
def test_listing_assets(user: User, notes: list[Note]) -> None:
    """Listing assets works as expected, with all types successfully resolved."""
    query = """
        query {
          assets(first: 10) {
            nodes {
              __typename
              ... on Note { content }
            }
          }
        }
    """

    result = api.execute_sync(query, None)
    assert result.errors is None
    assert result.data == {
        "assets": {
            "nodes": [
                {"__typename": "Note", "content": notes[1].content},
                {"__typename": "Note", "content": notes[5].content},
            ]
        }
    }

    result = api.execute_sync(query, user)
    assert result.errors is None
    assert result.data is not None
    assert result.data == {
        "assets": {
            "nodes": [
                {"__typename": "Note", "content": note.content}
                # Note that we expect assets to be ordered by their timestamp. That
                # means they are ordered chronologically, with the oldest entry first.
                # This is so that the connection API with 'first', 'after', etc. makes
                # more sense.
                for note in notes
            ]
        }
    }


@pytest.mark.django_db
def test_asset_pagination(user: User, notes: list[Note]) -> None:
    """Paginating through assets in both directions works as expected."""
    expected_nodes = [
        {"__typename": "Note", "content": note.content}
        for note in Note.objects.order_by("import_timestamp")
    ]

    # Forwards

    result = api.execute_sync(ASSET_PAGINATION_QUERY, user, first=6)
    assert result.errors is None
    assert result.data is not None
    assert result.data["assets"]["nodes"] == expected_nodes[:6]
    cursor = result.data["assets"]["pageInfo"]["endCursor"]
    assert isinstance(cursor, str)
    assert result.data["assets"]["pageInfo"]["hasNextPage"]

    result = api.execute_sync(ASSET_PAGINATION_QUERY, user, first=6, after=cursor)
    assert result.errors is None
    assert result.data is not None
    assert result.data["assets"]["nodes"] == expected_nodes[6:]
    assert not result.data["assets"]["pageInfo"]["hasNextPage"]

    # Backwards

    result = api.execute_sync(ASSET_PAGINATION_QUERY, user, last=6)
    assert result.errors is None
    assert result.data is not None
    assert result.data["assets"]["nodes"] == expected_nodes[-6:]
    cursor = result.data["assets"]["pageInfo"]["startCursor"]
    assert isinstance(cursor, str)
    assert result.data["assets"]["pageInfo"]["hasPreviousPage"]

    result = api.execute_sync(ASSET_PAGINATION_QUERY, user, last=6, before=cursor)
    assert result.errors is None
    assert result.data is not None
    assert result.data["assets"]["nodes"] == expected_nodes[:-6]
    assert not result.data["assets"]["pageInfo"]["hasPreviousPage"]


@pytest.mark.django_db
def test_pagination_by_timestamp(user: User, notes: list[Note]) -> None:
    """Specifying a timestamp works as an alternative to cursors for pagination."""
    result = api.execute_sync(ASSET_PAGINATION_QUERY, user, first=2, after="2022-01-05")
    assert result.errors is None
    assert result.data is not None
    assert result.data["assets"]["nodes"] == [
        {"__typename": "Note", "content": "Seventh note."},
        {"__typename": "Note", "content": "Eighth note."},
    ]
    assert result.data["assets"]["pageInfo"]["hasPreviousPage"] is True
    assert result.data["assets"]["pageInfo"]["hasNextPage"] is True
    start_cursor = result.data["assets"]["pageInfo"]["startCursor"]
    end_cursor = result.data["assets"]["pageInfo"]["endCursor"]

    result = api.execute_sync(ASSET_PAGINATION_QUERY, user, first=2, after=end_cursor)
    assert result.errors is None
    assert result.data is not None
    assert result.data["assets"]["nodes"] == [
        {"__typename": "Note", "content": "Ninth note."},
        {"__typename": "Note", "content": "Tenth note."},
    ]

    result = api.execute_sync(ASSET_PAGINATION_QUERY, user, last=2, before=start_cursor)
    assert result.errors is None
    assert result.data is not None
    assert result.data["assets"]["nodes"] == [
        {"__typename": "Note", "content": "Fifth note."},
        {"__typename": "Note", "content": "Sixth note."},
    ]

    result = api.execute_sync(
        ASSET_PAGINATION_QUERY, user, last=2, before="2022-01-02T03:20"
    )
    assert result.errors is None
    assert result.data is not None
    assert result.data["assets"]["nodes"] == [
        {"__typename": "Note", "content": "First note."},
        {"__typename": "Note", "content": "Second note."},
    ]
    assert result.data["assets"]["pageInfo"]["hasPreviousPage"] is False
    assert result.data["assets"]["pageInfo"]["hasNextPage"] is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    "filter,result_subset",
    [
        (
            # Find all assets from 4. January.
            {"mediaTimestamp": {"month": {"include": [1]}, "day": {"include": [4]}}},
            [0, 1, 3, 4, 5],
        ),
        (
            # Find all assets after 2022.
            {"mediaTimestamp": {"year": {"minimum": 2022}}},
            [2, 3, 4, 5, 6, 7, 8, 9],
        ),
        (
            # Find all assets after 2022, again.
            {"mediaTimestamp": {"after": "2022-01-01"}},
            [2, 3, 4, 5, 6, 7, 8, 9],
        ),
        (
            # This should return all assets with internal, member-only and unset
            # visibility settings, because the library's default value is member-only.
            {"visibility": {"public": False, "owners": False}},
            [0, 2, 3, 6, 7, 9],
        ),
        (
            # This time, exclude visibility settings inherited from the library.
            {
                "visibility": {
                    "public": False,
                    "owners": False,
                    "membersFromLibrary": False,
                }
            },
            [2, 3, 6, 7],
        ),
        (
            # Public assets from before 2022.
            {
                "visibility": {
                    "internal": False,
                    "members": False,
                    "owners": False,
                },
                "mediaTimestamp": {
                    "year": {"maximum": 2022, "inclusiveMaximum": False}
                },
            },
            [1],
        ),
        (
            # Nothing.
            {"includeNotes": False},
            [],
        ),
    ],
)
def test_asset_filtering(
    user: User, notes: list[Note], filter: dict[Any, Any], result_subset: list[int]
) -> None:
    expected_nodes = [
        {"__typename": "Note", "content": notes[index].content}
        for index in result_subset
    ]

    result = api.execute_sync(
        """query GetAsset($filter: AssetFilter!) {
            assets(first: 10, filter: $filter) {
                nodes {
                    __typename
                    ... on Note { content }
                }
            }
        }""",
        user,
        filter=filter,
    )
    assert result.errors is None
    assert result.data is not None
    assert result.data["assets"]["nodes"] == expected_nodes


@pytest.mark.django_db
def test_asset_stacking(user: User, notes: list[Note]) -> None:
    # Get all the node IDs from 2022. Stack them together later.
    result = api.execute_sync(
        """query {
            assets(
                first: 10,
                filter: {mediaTimestamp: {year: {include: [2022]}}},
            ) {
                nodes { id }
            }
        }""",
        user,
    )
    assert result.errors is None
    assert result.data is not None
    node_ids = [node["id"] for node in result.data["assets"]["nodes"]]

    stack_mutation = """
        mutation StackAssets($ids: [ID!]!) {
            stackAssets(input: {ids: $ids}) {
                __typename
                ... on StackingMutationSuccess { stackSize }
            }
        }
    """

    result = api.execute_sync(stack_mutation, None, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "stackAssets": {"__typename": "StackingMutationSuccess", "stackSize": 0}
    }

    other_user = User.objects.create_user("carl")
    result = api.execute_sync(stack_mutation, other_user, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "stackAssets": {"__typename": "StackingMutationSuccess", "stackSize": 0}
    }

    result = api.execute_sync(stack_mutation, user, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "stackAssets": {"__typename": "StackingMutationSuccess", "stackSize": 7}
    }

    result = api.execute_sync(
        """mutation SetRepresentative($id: ID!) {
            setStackRepresentative(id: $id) {
                __typename
                ... on SetStackRepresentativeSuccess {
                     representative {
                        ... on Note { content }
                    }
                }
            }
        }""",
        user,
        id=node_ids[1],  # This is notes[3].
    )
    assert result.errors is None
    assert result.data == {
        "setStackRepresentative": {
            "__typename": "SetStackRepresentativeSuccess",
            "representative": {"content": "Fourth note."},
        }
    }

    result = api.execute_sync(
        """query {
            assets(first: 10) {
                nodes {
                    ... on Note { content }
                }
            }
        }""",
        user,
    )
    assert result.errors is None
    assert result.data == {
        "assets": {
            "nodes": [
                {"content": "First note."},
                {"content": "Second note."},
                {"content": "Fourth note."},
                {"content": "Tenth note."},
            ]
        }
    }

    result = api.execute_sync(
        """query {
            assets(first: 10, filter: {useStacks: false}) {
                nodes {
                    ... on Note { content }
                }
            }
        }""",
        user,
    )
    assert result.errors is None
    assert result.data == {
        "assets": {
            "nodes": [
                {"content": "First note."},
                {"content": "Second note."},
                {"content": "Third note."},
                {"content": "Fourth note."},
                {"content": "Fifth note."},
                {"content": "Sixth note."},
                {"content": "Seventh note."},
                {"content": "Eighth note."},
                {"content": "Ninth note."},
                {"content": "Tenth note."},
            ]
        }
    }

    for node_id in node_ids:
        result = api.execute_sync(
            """query StackedWith($id: ID!) {
                assets(first: 10, filter: {stackedWith: $id}) {
                    nodes {
                        ... on Note { content }
                    }
                }
            }""",
            user,
            id=node_id,
        )
        assert result.errors is None
        assert result.data == {
            "assets": {
                "nodes": [
                    {"content": "Third note."},
                    {"content": "Fourth note."},
                    {"content": "Fifth note."},
                    {"content": "Sixth note."},
                    {"content": "Seventh note."},
                    {"content": "Eighth note."},
                    {"content": "Ninth note."},
                ]
            }
        }

    unstack_mutation = """
        mutation UnstackAssets($ids: [ID!]!) {
            unstackAssets(input: {ids: $ids}) {
                __typename
                ... on StackingMutationSuccess { stackSize }
            }
        }
    """

    result = api.execute_sync(unstack_mutation, None, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "unstackAssets": {
            "__typename": "StackingMutationSuccess",
            "stackSize": 0,
        }
    }

    result = api.execute_sync(unstack_mutation, other_user, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "unstackAssets": {
            "__typename": "StackingMutationSuccess",
            "stackSize": 0,
        }
    }

    result = api.execute_sync(unstack_mutation, user, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "unstackAssets": {
            "__typename": "StackingMutationSuccess",
            "stackSize": 7,
        }
    }


@hypothesis.settings(deadline=None)
@hypothesis.given(st.integers(0, 1000), st.integers(10, 50), st.data())
def test_asset_time_chunks(
    django_executor: Any, asset_count: int, target_size: int, data: st.DataObject
) -> None:
    user = User.objects.create()
    library = create_library(user)
    for _ in range(asset_count):
        Note.objects.create(
            library=library, content="", media_timestamp=data.draw(st.datetimes())
        )

    query = """
        query AssetTimeChunks($size: Int!) {
            assets {
                timeChunks(targetSize: $size) {
                    afterCursor
                    beforeCursor
                    startTimestamp
                    endTimestamp
                    size
                }
            }
        }

        query AssetTimestamps($after: String!, $before: String!, $count: Int!) {
            assets(after: $after, before: $before, first: $count) {
                nodes {
                    mediaTimestamp
                }
            }
        }
    """

    result = api.execute_sync(
        query, user, operation_name="AssetTimeChunks", size=target_size
    )
    assert result.errors is None
    assert result.data is not None

    total_count = 0
    chunk_count = len(result.data["assets"]["timeChunks"])
    for chunk_index, chunk in enumerate(result.data["assets"]["timeChunks"]):
        chunk_result = api.execute_sync(
            query,
            user,
            operation_name="AssetTimestamps",
            after=chunk["afterCursor"],
            before=chunk["beforeCursor"],
            count=int(1.5 * target_size),
        )
        assert chunk_result.errors is None
        assert chunk_result.data is not None
        chunk_nodes = chunk_result.data["assets"]["nodes"]

        assert len(chunk_nodes) == chunk["size"]
        if chunk_index < chunk_count - 1:
            # The last chunk (or the only chunk for small datasets) might be smaller,
            # but all other chunks should have a minimumm size.
            assert 0.5 * target_size <= chunk["size"]
        assert chunk["size"] <= 1.5 * target_size
        total_count += chunk["size"]

        assert chunk_nodes[0]["mediaTimestamp"] == chunk["startTimestamp"]
        assert chunk_nodes[-1]["mediaTimestamp"] == chunk["endTimestamp"]

    assert total_count == asset_count
