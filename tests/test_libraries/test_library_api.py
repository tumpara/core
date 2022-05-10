from typing import Optional

import pytest

from tumpara import api
from tumpara.accounts.models import Permission, User
from tumpara.libraries.models import Library, Visibility

mutation = """
    fragment Result on LibraryMutationResult {
        __typename
        ... on FormError {
            fields
            codes
        }
        ... on NodeError {
            requestedId
        }
        ... on Library {
            id
            source
            context
        }
    }

    mutation CreateLibrary($input: CreateLibraryInput!) {
        createLibrary(input: $input) {
            ...Result
        }
    }

    mutation UpdateLibrary($input: UpdateLibraryInput!) {
        updateLibrary(input: $input) {
            ...Result
        }
    }
"""


@pytest.mark.django_db
def test_library_listing() -> None:
    query = """
        query ListLibraries {
            libraries(first: 10) {
                nodes {
                    __typename
                    context
                }
            }
        }
    """
    Library.objects.create(source="testing://", context="test_storage")
    Library.objects.create(source="testing:///", context="test_storage")

    result = api.execute_sync(query, None)
    assert result.errors is None
    assert result.data == {"libraries": {"nodes": []}}

    superuser = User.objects.create_superuser("bob")

    result = api.execute_sync(query, superuser)
    assert result.errors is None
    assert result.data == {
        "libraries": {
            "nodes": [
                {"__typename": "Library", "context": "test_storage"},
                {"__typename": "Library", "context": "test_storage"},
            ]
        }
    }


@pytest.mark.django_db
def test_library_creating() -> None:
    result = api.execute_sync(
        mutation,
        None,
        "CreateLibrary",
        input={"source": "testing:///", "context": "test_storage"},
    )
    assert result.errors is None
    assert result.data == {
        "createLibrary": {
            "__typename": "NodeError",
            "requestedId": None,
        }
    }

    user = User.objects.create_user("bob")

    # All logged-in users have permission to create libraries.
    result = api.execute_sync(
        mutation,
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
    _, library_pk = api.decode_key(result.data["createLibrary"]["id"])
    library = Library.objects.get()
    assert str(library.pk) == library_pk
    assert library.source == "testing:///"
    assert library.context == "test_storage"
    assert library.default_visibility == Visibility.PUBLIC

    # Check whether the user now has appropriate permissions.
    user = User.objects.get()
    assert not user.has_perm("libraries.view_library")
    assert user.has_perm("libraries.view_library", library)
    assert user.has_perm("libraries.change_library", library)
    assert user.has_perm("libraries.delete_library", library)


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
