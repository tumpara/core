from typing import Optional

import pytest

from tumpara import api
from tumpara.accounts.models import User
from tumpara.libraries.models import Collection, Note

from ..test_accounts.utils import user_dataset  # noqa: F401
from ..test_accounts.utils import UserDataset
from .test_assets_api import library, notes  # noqa: F401
from .test_notes_api import user  # noqa: F401


@pytest.mark.django_db
def test_collection_listing(user_dataset: UserDataset) -> None:
    bob, carl, *_ = user_dataset
    superuser = User.objects.create_superuser("gru")
    Collection.objects.create(title="First")
    second_collection = Collection.objects.create(title="Second")
    second_collection.add_membership(bob)
    second_collection.add_membership(carl, owner=True)

    def check(user: Optional[User], expected_titles: list[str]) -> None:
        result = api.execute_sync(
            """query {
                collections(first: 10) {
                    nodes {
                        __typename
                        title
                    }
                }
            }""",
            user,
        )
        assert result.errors is None
        assert result.data == {
            "collections": {
                "nodes": [
                    {"__typename": "Collection", "title": title}
                    for title in expected_titles
                ]
            }
        }

    check(None, [])
    check(bob, ["Second"])
    check(carl, ["Second"])
    check(superuser, ["First", "Second"])


mutation = """
    fragment Result on CollectionMutationResult {
        __typename
        ... on FormError {
            fields
            codes
        }
        ... on NodeError {
            requestedId
        }
        ... on Collection {
            id
            title
        }
    }

    mutation CreateCollection($input: CreateCollectionInput!) {
        createCollection(input: $input) {
            ...Result
        }
    }

    mutation UpdateCollection($input: UpdateCollectionInput!) {
        updateCollection(input: $input) {
            ...Result
        }
    }
"""


@pytest.mark.django_db
def test_collection_creating() -> None:
    result = api.execute_sync(
        mutation, None, "CreateCollection", input={"title": "Hello"}
    )
    assert result.errors is None
    assert result.data == {
        "createCollection": {
            "__typename": "NodeError",
            "requestedId": None,
        }
    }

    user = User.objects.create_user("bob")

    result = api.execute_sync(
        mutation, user, "CreateCollection", input={"title": "Hello"}
    )
    assert result.errors is None
    assert result.data is not None
    assert result.data["createCollection"]["__typename"] == "Collection"
    assert result.data["createCollection"]["title"] == "Hello"

    collection = Collection.objects.get()
    assert collection.title == "Hello"

    user = User.objects.get()
    assert not user.has_perm("libraries.view_collection")
    assert user.has_perm("libraries.view_collection", collection)
    assert user.has_perm("libraries.change_collection", collection)
    assert user.has_perm("libraries.delete_collection", collection)


@pytest.mark.django_db
def test_collection_updating(user: User, notes: Note) -> None:
    result = api.execute_sync(
        mutation, user, "CreateCollection", input={"title": "Hello"}
    )
    assert result.errors is None
    assert result.data is not None
    collection_id = result.data["createCollection"]["id"]
    collection = Collection.objects.get()

    def assert_forbidden(user: Optional[User]) -> None:
        result = api.execute_sync(
            mutation, user, "UpdateCollection", input={"id": collection_id}
        )
        assert result.errors is None
        assert result.data == {
            "updateCollection": {
                "__typename": "NodeError",
                "requestedId": collection_id,
            }
        }

    assert_forbidden(None)
    other_user = User.objects.create_user("carl")
    assert_forbidden(other_user)
    collection.add_membership(other_user)  # Not an owner
    other_user = User.objects.get(username="carl")
    assert_forbidden(other_user)

    result = api.execute_sync(
        mutation, user, "UpdateCollection", input={"id": collection_id, "title": "Bye"}
    )
    assert result.errors is None
    assert result.data == {
        "updateCollection": {
            "__typename": "Collection",
            "id": collection_id,
            "title": "Bye",
        }
    }
    collection.refresh_from_db()
    assert collection.title == "Bye"

    result = api.execute_sync(
        """query {
            assets(first: 10) {
                nodes { id }
            }
        }""",
        user,
    )
    assert result.errors is None
    assert result.data is not None
    asset_ids = [node["id"] for node in result.data["assets"]["nodes"]]
    # Make sure we have all available notes, because we use that in the assertions
    # later.
    assert len(asset_ids) == Note.objects.count()

    result = api.execute_sync(
        mutation,
        user,
        "UpdateCollection",
        input={"id": collection_id, "addAssetIds": asset_ids},
    )
    assert result.errors is None
    assert result.data is not None
    assert collection.assets.count() == len(asset_ids)

    result = api.execute_sync(
        mutation,
        user,
        "UpdateCollection",
        input={"id": collection_id, "removeAssetIds": asset_ids},
    )
    assert result.errors is None
    assert result.data is not None
    assert collection.assets.count() == 0
