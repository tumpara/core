from typing import Any

import pytest
from django.utils import timezone

from tumpara import api
from tumpara.accounts.models import User
from tumpara.gallery.models import Note
from tumpara.libraries.models import Library, Visibility

from .test_notes_api import user  # noqa: F401


@pytest.fixture
def library(user: User) -> Library:
    library = Library.objects.create(source="testing:///", context="test_storage")
    library.add_membership(user, owner=True)
    return library


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
def test_listing_records(user: User, notes: list[Note]) -> None:
    """Listing gallery records works as expected, with all types successfully
    resolved."""
    query = """
        query {
          galleryRecords(first: 10) {
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
        "galleryRecords": {
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
        "galleryRecords": {
            "nodes": [
                {"__typename": "Note", "content": note.content}
                # Note that we expect gallery records to be ordered by their timestamp.
                # That means they are ordered chronologically, with the oldest entry
                # first. This is so that the connection API with 'first', 'after', etc.
                # makes more sense.
                for note in notes
            ]
        }
    }


@pytest.mark.django_db
def test_record_pagination(user: User, notes: list[Note]) -> None:
    """Paginating through records in both directions works as expected."""
    query = """
        query GalleryRecordPagination($after: String, $before: String, $first: Int, $last: Int) {
          galleryRecords(after: $after, before: $before, first: $first, last: $last) {
            pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
            nodes {
              __typename
              ... on Note { content }
            }
          }
        }
    """

    expected_nodes = [
        {"__typename": "Note", "content": note.content}
        for note in Note.objects.order_by("media_timestamp")
    ]

    # Forwards

    result = api.execute_sync(query, user, first=6)
    assert result.errors is None
    assert result.data is not None
    assert result.data["galleryRecords"]["nodes"] == expected_nodes[:6]
    cursor = result.data["galleryRecords"]["pageInfo"]["endCursor"]
    assert isinstance(cursor, str)
    assert result.data["galleryRecords"]["pageInfo"]["hasNextPage"]

    result = api.execute_sync(query, user, first=6, after=cursor)
    assert result.errors is None
    assert result.data is not None
    assert result.data["galleryRecords"]["nodes"] == expected_nodes[6:]
    assert not result.data["galleryRecords"]["pageInfo"]["hasNextPage"]

    # Backwards

    result = api.execute_sync(query, user, last=6)
    assert result.errors is None
    assert result.data is not None
    assert result.data["galleryRecords"]["nodes"] == expected_nodes[-6:]
    cursor = result.data["galleryRecords"]["pageInfo"]["startCursor"]
    assert isinstance(cursor, str)
    assert result.data["galleryRecords"]["pageInfo"]["hasPreviousPage"]

    result = api.execute_sync(query, user, last=6, before=cursor)
    assert result.errors is None
    assert result.data is not None
    assert result.data["galleryRecords"]["nodes"] == expected_nodes[:-6]
    assert not result.data["galleryRecords"]["pageInfo"]["hasPreviousPage"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "filter,result_subset",
    [
        (
            # Find all records from 4. January.
            {"mediaTimestamp": {"month": {"include": [1]}, "day": {"include": [4]}}},
            [0, 1, 3, 4, 5],
        ),
        (
            # Find all records after 2022.
            {"mediaTimestamp": {"year": {"minimum": 2022}}},
            [2, 3, 4, 5, 6, 7, 8, 9],
        ),
        (
            # Find all records after 2022, again.
            {"mediaTimestamp": {"after": "2022-01-01"}},
            [2, 3, 4, 5, 6, 7, 8, 9],
        ),
        (
            # This should return all records with internal, member-only and unset
            # visibility settings, because the library's default value is member-only.
            {"visibility": {"public": False, "owners": False}},
            [0, 2, 3, 6, 7, 9],
        ),
        (
            # This time, exclude visiblity settings inherited from the library.
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
            # Public records from before 2022.
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
    ],
)
def test_record_filtering(
    user: User, notes: list[Note], filter: dict, result_subset: list[int]
) -> None:
    expected_nodes = [
        {"__typename": "Note", "content": notes[index].content}
        for index in result_subset
    ]

    result = api.execute_sync(
        """query GetRecord($filter: GalleryRecordFilter!) {
            galleryRecords(first: 10, filter: $filter) {
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
    assert result.data["galleryRecords"]["nodes"] == expected_nodes


@pytest.mark.django_db
def test_record_stacking(user: User, notes: list[Note]):
    # Get all the node IDs from 2022. Stack them together later.
    result = api.execute_sync(
        """query {
            galleryRecords(
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
    node_ids = [node["id"] for node in result.data["galleryRecords"]["nodes"]]

    stack_mutation = """
        mutation StackRecords($ids: [ID!]!) {
            stackGalleryRecords(input: {ids: $ids}) {
                __typename
                ... on StackingMutationSuccess { stackSize }
            }
        }
    """

    result = api.execute_sync(stack_mutation, None, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "stackGalleryRecords": {"__typename": "StackingMutationSuccess", "stackSize": 0}
    }

    other_user = User.objects.create_user("carl")
    result = api.execute_sync(stack_mutation, other_user, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "stackGalleryRecords": {"__typename": "StackingMutationSuccess", "stackSize": 0}
    }

    result = api.execute_sync(stack_mutation, user, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "stackGalleryRecords": {"__typename": "StackingMutationSuccess", "stackSize": 7}
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
            galleryRecords(first: 10) {
                nodes {
                    ... on Note { content }
                }
            }
        }""",
        user,
    )
    assert result.errors is None
    assert result.data == {
        "galleryRecords": {
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
            galleryRecords(first: 10, filter: {useStacks: false}) {
                nodes {
                    ... on Note { content }
                }
            }
        }""",
        user,
    )
    assert result.errors is None
    assert result.data == {
        "galleryRecords": {
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

    unstack_mutation = """
        mutation UnstackRecords($ids: [ID!]!) {
            unstackGalleryRecords(input: {ids: $ids}) {
                __typename
                ... on StackingMutationSuccess { stackSize }
            }
        }
    """

    result = api.execute_sync(unstack_mutation, None, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "unstackGalleryRecords": {
            "__typename": "StackingMutationSuccess",
            "stackSize": 0,
        }
    }

    result = api.execute_sync(unstack_mutation, other_user, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "unstackGalleryRecords": {
            "__typename": "StackingMutationSuccess",
            "stackSize": 0,
        }
    }

    result = api.execute_sync(unstack_mutation, user, ids=node_ids)
    assert result.errors is None
    assert result.data == {
        "unstackGalleryRecords": {
            "__typename": "StackingMutationSuccess",
            "stackSize": 7,
        }
    }
