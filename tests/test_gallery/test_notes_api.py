from typing import Optional

import pytest

from tumpara import api
from tumpara.accounts.models import User
from tumpara.gallery.models import Note
from tumpara.libraries.models import Library

from ..test_libraries.test_library_api import mutation as create_library_mutation

mutation = """
    fragment Result on NoteMutationResult {
        __typename
        ... on FormError {
            fields
            codes
        }
        ... on NodeError {
            requestedId
        }
        ... on Note {
            id
            library { id }
            content
        }
    }

    mutation CreateNote($input: CreateNoteInput!) {
        createNote(input: $input) {
            ...Result
        }
    }

    mutation UpdateNote($input: UpdateNoteInput!) {
        updateNote(input: $input) {
            ...Result
        }
    }
"""


@pytest.fixture
def user() -> User:
    return User.objects.create_user("bob")


@pytest.fixture
def library_id(user: User) -> str:
    result = api.execute_sync(
        create_library_mutation,
        user,
        "CreateLibrary",
        input={
            "source": "testing:///",
            "context": "test_storage",
            "defaultVisibility": "PUBLIC",
        },
    )
    assert result.errors is None
    assert result.data is not None
    assert result.data["createLibrary"]["__typename"] == "Library"
    library_id = result.data["createLibrary"]["id"]
    assert isinstance(library_id, str)
    return library_id


@pytest.mark.django_db
def test_note_creating(user: User, library_id: str) -> None:
    def assert_forbidden(user: Optional[User]) -> None:
        result = api.execute_sync(
            mutation,
            user,
            "CreateNote",
            input={"content": "Test", "library": library_id},
        )
        assert result.errors is None
        assert result.data == {
            "createNote": {
                "__typename": "NodeError",
                "requestedId": library_id,
            }
        }

    assert_forbidden(None)
    # Another user (that doesn't own the library) shouldn't be able to create a note.
    other_user = User.objects.create_user("carl")
    assert_forbidden(other_user)

    result = api.execute_sync(
        mutation,
        user,
        "CreateNote",
        input={"content": "Test", "library": library_id},
    )
    assert result.errors is None
    assert result.data is not None
    assert result.data["createNote"]["__typename"] == "Note"
    assert result.data["createNote"]["library"]["id"] == library_id
    _, note_pk = api.decode_key(result.data["createNote"]["id"])
    note = Note.objects.get()
    assert str(note.pk) == note_pk
    _, library_pk = api.decode_key(library_id)
    assert str(note.library.pk) == library_pk
    assert note.content == "Test"


@pytest.mark.django_db
def test_note_editing(user: User, library_id: str) -> None:
    result = api.execute_sync(
        mutation,
        user,
        "CreateNote",
        input={"content": "Foo", "library": library_id},
    )
    assert result.data is not None
    note_id = result.data["createNote"]["id"]

    def assert_forbidden(user: Optional[User]) -> None:
        result = api.execute_sync(
            mutation,
            user,
            "UpdateNote",
            input={"id": note_id, "content": "Bar"},
        )
        assert result.errors is None
        assert result.data == {
            "updateNote": {
                "__typename": "NodeError",
                "requestedId": note_id,
            }
        }

    assert_forbidden(None)
    other_user = User.objects.create_user("carl")
    assert_forbidden(other_user)
    Library.objects.get().add_membership(other_user)
    # Carl is not an owner, so he should not be allowed to edit the note.
    assert_forbidden(other_user)

    result = api.execute_sync(
        mutation,
        user,
        "UpdateNote",
        input={"id": note_id, "content": "Bar"},
    )
    assert result.errors is None
    assert result.data == {
        "updateNote": {
            "__typename": "Note",
            "id": note_id,
            "library": {"id": library_id},
            "content": "Bar",
        }
    }
    assert Note.objects.get().content == "Bar"
