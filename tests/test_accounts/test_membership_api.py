import pytest

from tumpara import api

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
