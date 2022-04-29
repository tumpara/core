from typing import Optional

import pytest

from tumpara import api
from tumpara.accounts import models as accounts_models
from tumpara.libraries import models as libraries_models

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
    libraries_models.Library.objects.create(source="testing://", context="test_storage")
    libraries_models.Library.objects.create(
        source="testing:///", context="test_storage"
    )

    result = api.execute_sync(query, None)
    assert result.errors is None
    assert result.data == {"libraries": {"nodes": []}}

    superuser = accounts_models.User.objects.create_superuser("bob")

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

    user = accounts_models.User.objects.create_user("bob")

    # As long as the user doesn't have permission to create a library, this should not
    # work:
    result = api.execute_sync(
        mutation,
        user,
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

    user.user_permissions.add(
        accounts_models.Permission.objects.get_by_natural_key(
            "add_library", "libraries", "library"
        )
    )
    # Get a new user object because of the permission cache.
    user = accounts_models.User.objects.get()

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
    library = libraries_models.Library.objects.get()
    assert str(library.pk) == library_pk
    assert library.source == "testing:///"
    assert library.context == "test_storage"
    assert library.default_visibility == libraries_models.Visibility.PUBLIC

    # Check whether the user now has appropriate permissions.
    user = accounts_models.User.objects.get()
    assert not user.has_perm("libraries.view_library")
    assert user.has_perm("libraries.view_library", library)
    assert user.has_perm("libraries.change_library", library)
    assert user.has_perm("libraries.delete_library", library)


@pytest.mark.django_db
def test_library_editing() -> None:
    library = libraries_models.Library.objects.create(
        source="testing:///",
        context="test_storage",
        default_visibility=libraries_models.Visibility.PUBLIC,
    )

    superuser = accounts_models.User.objects.create_superuser("kevin")
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

    def assert_forbidden(user: Optional[accounts_models.User]) -> None:
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
    user = accounts_models.User.objects.create_user("bob")
    assert_forbidden(user)
    library.add_membership(user)
    user = accounts_models.User.objects.get(username="bob")
    assert_forbidden(user)

    library.add_membership(user, owner=True)
    user = accounts_models.User.objects.get(username="bob")

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
    assert library.default_visibility == libraries_models.Visibility.PUBLIC

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
    assert library.default_visibility == libraries_models.Visibility.INTERNAL

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
