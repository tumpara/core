import pytest

from tumpara import api
from tumpara.accounts.models import User

from .models import JoinableThing
from .utils import user_dataset  # noqa: F401
from .utils import UserDataset


@pytest.mark.django_db
def test_membership_listing(user_dataset: UserDataset) -> None:
    query = """
        query ThingMembers {
            joinableThings(first: 1) {
                nodes {
                    members(first: 2) {
                        edges {
                            owner
                            node {
                                username
                            }
                        }
                    }
                }
            }
        }
    """

    bob, carl, *_ = user_dataset
    thing = JoinableThing.objects.create()
    thing.add_membership(bob)
    thing.add_membership(carl, owner=True)

    result = api.execute_sync(query, None)
    assert result.errors is None
    assert result.data == {"joinableThings": {"nodes": []}}

    result = api.execute_sync(query, bob)
    assert result.errors is None
    assert result.data == {
        "joinableThings": {
            "nodes": [
                {
                    "members": {
                        "edges": [
                            {"owner": False, "node": {"username": "bob"}},
                            {"owner": True, "node": {"username": "carl"}},
                        ]
                    }
                }
            ]
        }
    }


@pytest.mark.django_db
def test_membership_setting(user_dataset: UserDataset) -> None:
    bob, carl, *_ = user_dataset
    thing = JoinableThing.objects.create()
    ids = {
        "bob": api.encode_key("User", bob.pk),
        "carl": api.encode_key("User", carl.pk),
        "thing": api.encode_key("JoinableThing", thing.pk),
    }
    superuser = User.objects.create_superuser("admin")

    result_fragment = """
        fragment Result on ManageMembershipResult {
            __typename
            ... on NodeError {
                requestedId
            }
        }
    """
    mutation = (
        result_fragment
        + """
        mutation SetMemberships($bob: ID!, $carl: ID!, $thing: ID!) {
            bob: manageMembership(
                input: {joinableId: $thing, userId: $bob, status: false}
            ) { ...Result }
            carl: manageMembership(
                input: {joinableId: $thing, userId: $carl, status: true}
            ) { ...Result }
        }
    """
    )

    result = api.execute_sync(mutation, None, **ids)
    assert result.errors is None
    assert result.data == {
        "bob": {"__typename": "NodeError", "requestedId": ids["thing"]},
        "carl": {"__typename": "NodeError", "requestedId": ids["thing"]},
    }

    result = api.execute_sync(mutation, superuser, **ids)
    assert result.errors is None
    assert result.data == {
        "bob": {"__typename": "ManageMembershipSuccess"},
        "carl": {"__typename": "ManageMembershipSuccess"},
    }

    assert set(thing.user_memberships.values_list("user__username", "is_owner")) == {
        ("bob", False),
        ("carl", True),
    }

    result = api.execute_sync(
        result_fragment
        + """mutation RemoveMemberships($bob: ID!, $carl: ID!, $thing: ID!) {
            bob: manageMembership(
                input: {joinableId: $thing, userId: $bob, status: null}
            ) { ...Result }
            carl: manageMembership(
                input: {joinableId: $thing, userId: $carl, status: null}
            ) { ...Result }
        }""",
        carl,
        **ids,
    )
    assert result.errors is None
    assert result.data == {
        "bob": {"__typename": "ManageMembershipSuccess"},
        "carl": {"__typename": "ManageMembershipSuccess"},
    }

    assert thing.user_memberships.count() == 0
