import pytest

from tumpara.accounts.models import User

UserDataset = tuple[User, User, User, User, User, User]


@pytest.fixture
def user_dataset() -> UserDataset:
    """Create a set of test users.

    The names are taken from `here`_.

    .. _here: https://www.getbeautified.com/minion-names/
    """
    bob = User.objects.create_user("bob")
    carl = User.objects.create_user("carl", "carl@minionsmovie.com")
    dave = User.objects.create_user("dave", full_name="Dave Minion")
    frank = User.objects.create_user("frank", short_name="Frank")
    jerry = User.objects.create_user(
        "jerry", full_name="Jerry Minion", short_name="Jerry"
    )
    kevin = User.objects.create_user(
        "kevin", "kevin@minionsmovie.com", full_name="Kevin Minion", short_name="Kevin"
    )

    return bob, carl, dave, frank, jerry, kevin
