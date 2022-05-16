from typing import Optional

import pytest

from tumpara import api
from tumpara.accounts.models import User, UserMembership
from tumpara.gallery.models import Album, Note

from ..test_accounts.utils import user_dataset  # noqa: F401
from ..test_accounts.utils import UserDataset
from .test_gallery_assets_api import library, notes  # noqa: F401
from .test_notes_api import user  # noqa: F401


@pytest.mark.django_db
def test_album_listing(user_dataset: UserDataset) -> None:
    bob, carl, *_ = user_dataset
    superuser = User.objects.create_superuser("gru")
    Album.objects.create(title="First")
    second_album = Album.objects.create(title="Second")
    second_album.add_membership(bob)
    second_album.add_membership(carl, owner=True)

    def check(user: Optional[User], expected_titles: list[str]) -> None:
        result = api.execute_sync(
            """query {
                albums(first: 10) {
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
            "albums": {
                "nodes": [
                    {"__typename": "Album", "title": title} for title in expected_titles
                ]
            }
        }

    check(None, [])
    check(bob, ["Second"])
    check(carl, ["Second"])
    check(superuser, ["First", "Second"])


mutation = """
    fragment Result on AlbumMutationResult {
        __typename
        ... on FormError {
            fields
            codes
        }
        ... on NodeError {
            requestedId
        }
        ... on Album {
            id
            title
        }
    }

    mutation CreateAlbum($input: CreateAlbumInput!) {
        createAlbum(input: $input) {
            ...Result
        }
    }

    mutation UpdateAlbum($input: UpdateAlbumInput!) {
        updateAlbum(input: $input) {
            ...Result
        }
    }
"""


@pytest.mark.django_db
def test_album_creating() -> None:
    result = api.execute_sync(mutation, None, "CreateAlbum", input={"title": "Hello"})
    assert result.errors is None
    assert result.data == {
        "createAlbum": {
            "__typename": "NodeError",
            "requestedId": None,
        }
    }

    user = User.objects.create_user("bob")

    result = api.execute_sync(mutation, user, "CreateAlbum", input={"title": "Hello"})
    assert result.errors is None
    assert result.data is not None
    assert result.data["createAlbum"]["__typename"] == "Album"
    assert result.data["createAlbum"]["title"] == "Hello"

    album = Album.objects.get()
    assert album.title == "Hello"

    user = User.objects.get()
    assert not user.has_perm("gallery.view_album")
    assert user.has_perm("gallery.view_album", album)
    assert user.has_perm("gallery.change_album", album)
    assert user.has_perm("gallery.delete_album", album)


@pytest.mark.django_db
def test_album_updating(user: User, notes: Note) -> None:
    result = api.execute_sync(mutation, user, "CreateAlbum", input={"title": "Hello"})
    assert result.errors is None
    album_id = result.data["createAlbum"]["id"]
    album = Album.objects.get()

    def assert_forbidden(user: Optional[User]) -> None:
        result = api.execute_sync(mutation, user, "UpdateAlbum", input={"id": album_id})
        assert result.errors is None
        assert result.data == {
            "updateAlbum": {
                "__typename": "NodeError",
                "requestedId": album_id,
            }
        }

    assert_forbidden(None)
    other_user = User.objects.create_user("carl")
    assert_forbidden(other_user)
    album.add_membership(other_user)  # Not an owner
    other_user = User.objects.get(username="carl")
    assert_forbidden(other_user)

    result = api.execute_sync(
        mutation, user, "UpdateAlbum", input={"id": album_id, "title": "Bye"}
    )
    assert result.errors is None
    assert result.data == {
        "updateAlbum": {"__typename": "Album", "id": album_id, "title": "Bye"}
    }
    album.refresh_from_db()
    assert album.title == "Bye"

    result = api.execute_sync(
        """query {
            galleryAssets(first: 10) {
                nodes { id }
            }
        }""",
        user,
    )
    assert result.errors is None
    assert result.data is not None
    asset_ids = [node["id"] for node in result.data["galleryAssets"]["nodes"]]
    # Make sure we have all available notes, because we use that in the assertions
    # later.
    assert len(asset_ids) == Note.objects.count()

    result = api.execute_sync(
        mutation, user, "UpdateAlbum", input={"id": album_id, "addAssetIds": asset_ids}
    )
    assert result.errors is None
    assert result.data is not None
    assert album.assets.count() == len(asset_ids)

    result = api.execute_sync(
        mutation,
        user,
        "UpdateAlbum",
        input={"id": album_id, "removeAssetIds": asset_ids},
    )
    assert result.errors is None
    assert result.data is not None
    assert album.assets.count() == 0
