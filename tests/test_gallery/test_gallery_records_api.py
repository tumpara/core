import pytest

from tumpara import api
from tumpara.accounts.models import User
from tumpara.gallery.models import Note
from tumpara.libraries.models import Library

from .test_notes_api import user  # noqa: F401


@pytest.fixture
def library(user: User) -> Library:
    library = Library.objects.create(source="testing:///", context="test_storage")
    library.add_membership(user, owner=True)
    return library


@pytest.fixture
def notes(library: Library) -> set[Note]:
    return {
        Note.objects.create(library=library, content="First note."),
        Note.objects.create(library=library, content="Second note."),
        Note.objects.create(library=library, content="Third note."),
        Note.objects.create(library=library, content="Fourth note."),
        Note.objects.create(library=library, content="Fifth note."),
        Note.objects.create(library=library, content="Sixth note."),
        Note.objects.create(library=library, content="Seventh note."),
        Note.objects.create(library=library, content="Eighth note."),
        Note.objects.create(library=library, content="Ninth note."),
        Note.objects.create(library=library, content="Tenth note."),
    }


@pytest.mark.django_db
def test_listing_records(user: User, notes: set[Note]) -> None:
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
    assert result.data == {"galleryRecords": {"nodes": []}}

    result = api.execute_sync(query, user)
    assert result.errors is None
    assert result.data is not None
    assert result.data == {
        "galleryRecords": {
            "nodes": [
                {"__typename": "Note", "content": note.content}
                # Note that we expect gallery records to be ordered by their timestamp.
                # This is so that the connection API with 'first', 'after', etc. makes
                # more sense.
                for note in Note.objects.order_by("media_timestamp")
            ]
        }
    }


@pytest.mark.django_db
def test_record_pagination(user: User, notes: set[Note]) -> None:
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
