from collections.abc import Mapping, Set
from typing import Any

import pytest

from tumpara.api import schema

from .utils import user_dataset  # noqa: F401
from .utils import UserDataset


@pytest.mark.parametrize(
    "filter,expected_users",
    [
        ({}, {"bob", "carl", "dave", "frank", "jerry", "kevin"}),
        ({"fullName": {"endsWith": "minion"}}, {"dave", "jerry", "kevin"}),
        # TODO Support this test under SQLite:
        #  ({"fullName": {"endsWith": "minion", "caseSensitive": True}}, {}),
        ({"anyName": {"contains": "Minion"}}, {"dave", "jerry", "kevin"}),
        ({"username": {"include": ["bob"]}}, {"bob"}),
    ],
)
@pytest.mark.django_db
def test_user_list(
    user_dataset: UserDataset, filter: Mapping[str, Any], expected_users: Set[str]
) -> None:
    """Logged-in users can list and search all the users on the server."""
    result = schema.execute_sync(
        """query FilterUsers($filter: UserFilter) {
            users(first: 10, filter: $filter) {
                nodes {
                    __typename
                    username
                }
            }
        }
        """,
        user_dataset[0],
        filter=filter,
    )
    assert result.errors is None
    assert result.data is not None
    for node in result.data["users"]["nodes"]:
        assert node["__typename"] == "User"
    assert {node["username"] for node in result.data["users"]["nodes"]} == set(
        expected_users
    )


@pytest.mark.django_db
def test_anonymous_user_list(user_dataset: UserDataset) -> None:
    """Anonymous sessions cannot list users."""
    result = schema.execute_sync(
        """query AllUsers {
            users(first: 10) {
                nodes { __typename }
            }
        }"""
    )
    assert result.errors is None
    assert result.data == {"users": {"nodes": []}}


@pytest.mark.django_db
def test_user_fields(user_dataset: UserDataset) -> None:
    """Special fields like the display name are calculated correctly."""
    result = schema.execute_sync(
        """query AllUsers {
            users(first: 10) {
                nodes {
                    username
                    displayName
                }
            }
        }
        """,
        user_dataset[0],
    )
    assert result.errors is None
    assert result.data is not None
    assert result.data["users"]["nodes"] == [
        dict(username="bob", displayName="bob"),
        dict(username="carl", displayName="carl"),
        dict(username="dave", displayName="Dave Minion"),
        dict(username="frank", displayName="Frank"),
        dict(username="jerry", displayName="Jerry"),
        dict(username="kevin", displayName="Kevin"),
    ]


@pytest.mark.django_db
def test_user_access_by_id(user_dataset: UserDataset) -> None:
    """User profiles can be accessed by their node id, but only by logged-in users."""
    result = schema.execute_sync(
        """query UserIds {
            users(first: 10) {
                nodes { id }
            }
        }""",
        user_dataset[0],
    )
    assert result.errors is None
    assert result.data is not None
    nodes = result.data["users"]["nodes"]
    seen_usernames = set[str]()

    query = """query GetUserById($id: ID!) {
        node (id: $id) {
            __typename
            ...on User {
                username
            }
        }
    }"""

    for node in nodes:
        result = schema.execute_sync(query, user_dataset[0], id=node["id"])
        assert result.errors is None
        assert result.data is not None
        assert result.data["node"]["__typename"] == "User"
        seen_usernames.add(result.data["node"]["username"])

    assert seen_usernames == {user.username for user in user_dataset}

    for node in nodes:
        result = schema.execute_sync(query, id=node["id"])
        assert result.errors is None
        assert result.data is not None
        assert result.data["node"] is None
