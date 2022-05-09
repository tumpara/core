from typing import Optional

import pytest

from tumpara import api
from tumpara.accounts.models import Permission, User
from tumpara.libraries.models import Library, Visibility

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
        updateLibrary(input: $input) {
            ...Result
        }
    }
"""


@pytest.fixture
def user() -> User:
    user = User.objects.create_user("bob")
    user.user_permissions.add(
        Permission.objects.get_by_natural_key("add_library", "libraries", "library")
    )
    return user


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
    result = api.execute_sync(
        mutation,
        None,
        "CreateNote",
        input={"content": "Test", "library": library_id},
    )
    assert result.errors is None
    assert result.data == {
        "createLibrary": {
            "__typename": "NodeError",
            "requestedId": None,
        }
    }


@pytest.mark.django_db
def test_library_editing() -> None:
    library = Library.objects.create(
        source="testing:///",
        context="test_storage",
        default_visibility=Visibility.PUBLIC,
    )

    superuser = User.objects.create_superuser("kevin")
    result = api.execute_sync(
        """
            query {
                libraries(first:1) {
                    nodes {
                        id
                    }
                }
            }
        """,
        superuser,
    )
    assert result.data is not None
    library_id = result.data["libraries"]["nodes"][0]["id"]

    def assert_forbidden(user: Optional[User]) -> None:
        result = api.execute_sync(
            mutation, user, "UpdateLibrary", input={"id": library_id}
        )
        assert result.errors is None
        assert result.data == {
            "updateLibrary": {
                "__typename": "NodeError",
                "requestedId": library_id,
            }
        }

    assert_forbidden(None)
    user = User.objects.create_user("bob")
    assert_forbidden(user)
    library.add_membership(user)
    user = User.objects.get(username="bob")
    assert_forbidden(user)

    library.add_membership(user, owner=True)
    user = User.objects.get(username="bob")

    # Giving no options shouldn't update anything.
    result = api.execute_sync(
        mutation,
        user,
        "UpdateLibrary",
        input={"id": library_id},
    )
    assert result.errors is None
    library.refresh_from_db()
    assert library.source == "testing:///"
    assert library.default_visibility == Visibility.PUBLIC

    # Giving both options should update them.
    result = api.execute_sync(
        mutation,
        user,
        "UpdateLibrary",
        input={
            "id": library_id,
            "source": "testing:///hi",
            "defaultVisibility": "INTERNAL",
        },
    )
    assert result.errors is None
    assert result.data is not None
    assert result.data["updateLibrary"]["__typename"] == "Library"
    library.refresh_from_db()
    assert library.source == "testing:///hi"
    assert library.default_visibility == Visibility.INTERNAL

    # Validation errors should be passed along.
    result = api.execute_sync(
        mutation,
        user,
        "UpdateLibrary",
        input={
            "id": library_id,
            "source": "lol://notavailable",
        },
    )
    assert result.errors is None
    assert result.data == {
        "updateLibrary": {
            "__typename": "FormError",
            "fields": ["source"],
            "codes": ["unsupported_storage_scheme"],
        }
    }
