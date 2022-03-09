from typing import Any

import hypothesis
import pytest

from tumpara.accounts.models import AnonymousUser, User
from tumpara.testing import strategies as st

from .models import JoinableThing
from .utils import user_dataset  # noqa: F401
from .utils import UserDataset

change_thing_permission = "test_accounts.change_joinablething"
delete_thing_permission = "test_accounts.delete_joinablething"
view_thing_permission = "test_accounts.view_joinablething"
supported_permissions = (
    view_thing_permission,
    change_thing_permission,
    delete_thing_permission,
)


@pytest.mark.django_db
def test_regular_user_permissions(user_dataset: UserDataset) -> None:
    """Permission checks on :class:`User` instances work as expected when adding them
    to joinables."""
    bob, carl, dave, *_ = user_dataset
    thing = JoinableThing.objects.create()

    for user in (bob, carl, dave):
        # Make sure the permissions aren't set globally first. That way we are actually
        # testing the per-object permissions below.
        assert not user.has_perm(change_thing_permission)
        assert not user.has_perm(delete_thing_permission)
        assert not user.has_perm(view_thing_permission)

        assert not user.has_perm(change_thing_permission, thing)
        assert not user.has_perm(delete_thing_permission, thing)
        assert not user.has_perm(view_thing_permission, thing)

    thing.add_membership(carl)
    thing.add_membership(dave, owner=True)

    assert not bob.has_perm(change_thing_permission, thing)
    assert not bob.has_perm(delete_thing_permission, thing)
    assert not bob.has_perm(view_thing_permission, thing)

    assert not carl.has_perm(change_thing_permission, thing)
    assert not carl.has_perm(delete_thing_permission, thing)
    assert carl.has_perm(view_thing_permission, thing)

    assert dave.has_perm(change_thing_permission, thing)
    assert dave.has_perm(delete_thing_permission, thing)
    assert dave.has_perm(view_thing_permission, thing)


@pytest.mark.django_db
def test_regular_user_bulk_permissions(user_dataset: UserDataset) -> None:
    """Bulk permission check work in the same way as regular permission checks."""
    first = JoinableThing.objects.create()
    second = JoinableThing.objects.create()
    (
        bob,  # No member
        carl,  # First: member, Second: nothing
        dave,  # First: member, Second: member
        frank,  # First: owner, Second: nothing
        jerry,  # First: owner, Second: member
        kevin,  # First: owner, Second: owner
    ) = user_dataset

    for user in user_dataset:
        assert not user.has_perms([change_thing_permission], first)
        assert not user.has_perms([delete_thing_permission], first)
        assert not user.has_perms([view_thing_permission], first)

    first.add_membership(carl)
    first.add_membership(dave)
    second.add_membership(dave)
    first.add_membership(frank, owner=True)
    first.add_membership(jerry, owner=True)
    second.add_membership(jerry)
    first.add_membership(kevin, owner=True)
    second.add_membership(kevin, owner=True)

    for user in (bob, carl, dave, frank, jerry, kevin):
        # Like in the last test, check for the general permissions first.
        assert not user.has_perms([change_thing_permission])
        assert not user.has_perms([delete_thing_permission])
        assert not user.has_perms([view_thing_permission])

    change_first = f"{change_thing_permission}__{first.pk}"
    delete_first = f"{delete_thing_permission}__{first.pk}"
    view_first = f"{view_thing_permission}__{first.pk}"
    change_second = f"{change_thing_permission}__{second.pk}"
    delete_second = f"{delete_thing_permission}__{second.pk}"
    view_second = f"{view_thing_permission}__{second.pk}"

    assert not bob.has_perms([change_first])
    assert not bob.has_perms([delete_first, change_second])
    assert not bob.has_perms([view_first])
    assert not bob.has_perms([view_thing_permission], first)

    assert carl.has_perms([view_first])
    assert carl.has_perms([view_thing_permission], first)
    assert not carl.has_perms([view_first, change_first])
    assert not carl.has_perms([view_second])

    assert dave.has_perms([view_first, view_second])
    assert not dave.has_perms([view_first, change_second])

    assert frank.has_perms([change_first, delete_first])
    assert not frank.has_perms([change_second, view_first])

    assert jerry.has_perms([change_first, view_first, delete_first, view_second])
    assert not jerry.has_perms([delete_first, delete_second])

    assert kevin.has_perms(
        [
            change_first,
            delete_first,
            view_first,
            change_second,
            delete_second,
            view_second,
        ]
    )


@pytest.mark.django_db
def test_queryset_permissions(user_dataset: UserDataset) -> None:
    first = JoinableThing.objects.create()
    second = JoinableThing.objects.create()
    third = JoinableThing.objects.create()
    fourth = JoinableThing.objects.create()
    bob, carl, dave, *_ = user_dataset

    for_user = JoinableThing.objects.for_user
    view_permission = view_thing_permission
    change_permission = change_thing_permission
    delete_permission = delete_thing_permission

    assert list(for_user(view_permission, bob)) == []
    assert list(for_user(change_permission, bob)) == []

    first.add_membership(carl)
    second.add_membership(carl)
    third.add_membership(carl)
    fourth.add_membership(carl)
    assert list(for_user(view_permission, carl)) == [first, second, third, fourth]
    assert list(for_user(change_permission, carl)) == []
    assert list(for_user(delete_permission, carl)) == []

    first.add_membership(dave)
    second.add_membership(dave)
    third.add_membership(dave, owner=True)
    fourth.add_membership(dave, owner=True)
    assert list(for_user(view_permission, dave)) == [first, second, third, fourth]
    assert list(for_user(change_permission, dave)) == [third, fourth]
    assert list(for_user(delete_permission, dave)) == [third, fourth]


@pytest.mark.django_db
def test_superuser_permissions() -> None:
    """Superusers have full access to joinables."""
    user = User.objects.create_superuser("uberadmin", None, None)
    thing = JoinableThing.objects.create()

    assert user.has_perm(change_thing_permission)
    assert user.has_perm(delete_thing_permission)
    assert user.has_perm(view_thing_permission)
    assert user.has_perm(change_thing_permission, thing)
    assert user.has_perm(delete_thing_permission, thing)
    assert user.has_perm(view_thing_permission, thing)


@pytest.mark.django_db
def test_superuser_bulk_permissions() -> None:
    """Superusers have full access when bulk checking permissions."""
    user = User.objects.create_superuser("uberadmin", None, None)
    first = JoinableThing.objects.create()
    second = JoinableThing.objects.create()

    change_first = f"{change_thing_permission}__{first.pk}"
    delete_first = f"{delete_thing_permission}__{first.pk}"
    view_first = f"{view_thing_permission}__{first.pk}"
    change_second = f"{change_thing_permission}__{second.pk}"
    delete_second = f"{delete_thing_permission}__{second.pk}"
    view_second = f"{view_thing_permission}__{second.pk}"

    assert user.has_perms(
        [
            change_first,
            delete_first,
            view_first,
            change_second,
            delete_second,
            view_second,
        ]
    )
    assert user.has_perms([change_first, view_first, change_second, view_second])
    assert user.has_perms([change_thing_permission], first)
    assert user.has_perms([view_thing_permission], second)


@pytest.mark.django_db
def test_anonymous_user_permissions() -> None:
    """Anonymous users have no access to joinables."""
    user = AnonymousUser()
    thing = JoinableThing.objects.create()

    assert not user.has_perm(change_thing_permission)
    assert not user.has_perm(delete_thing_permission)
    assert not user.has_perm(view_thing_permission)

    assert not user.has_perm(change_thing_permission, thing)
    assert not user.has_perm(delete_thing_permission, thing)
    assert not user.has_perm(view_thing_permission, thing)


@pytest.mark.django_db
def test_anonymous_bulk_permissions() -> None:
    """Anonymous users have no access when checking permissions in bulk."""
    user = AnonymousUser()
    first = JoinableThing.objects.create()
    second = JoinableThing.objects.create()

    change_first = f"{change_thing_permission}__{first.pk}"
    delete_first = f"{delete_thing_permission}__{first.pk}"
    view_first = f"{view_thing_permission}__{first.pk}"
    change_second = f"{change_thing_permission}__{second.pk}"
    delete_second = f"{delete_thing_permission}__{second.pk}"
    view_second = f"{view_thing_permission}__{second.pk}"

    assert not user.has_perms(
        [
            change_first,
            delete_first,
            view_first,
            change_second,
            delete_second,
            view_second,
        ]
    )
    assert not user.has_perms([change_first, view_first, change_second, view_second])
    assert not user.has_perms([change_thing_permission], first)
    assert not user.has_perms([view_thing_permission], second)


@hypothesis.given(st.data())
def test_joinable_for_user_query(django_executor: Any, data: st.DataObject) -> None:
    user = User.objects.create_user("user")
    superuser = User.objects.create_superuser("uberadmin", "" "")

    things = {
        JoinableThing.objects.create() for _ in range(data.draw(st.integers(4, 10)))
    }
    member_things = set[JoinableThing]()
    owned_things = set[JoinableThing]()

    for thing in things:
        match data.draw(st.integers(0, 2)):
            case 0:
                pass
            case 1:
                thing.add_membership(user)
                member_things.add(thing)
            case 2:
                thing.add_membership(user, owner=True)
                member_things.add(thing)
                owned_things.add(thing)

    assert (
        set(JoinableThing.objects.for_user(view_thing_permission, user))
        == member_things
    )
    assert (
        set(JoinableThing.objects.for_user(change_thing_permission, user))
        == owned_things
    )
    assert (
        set(JoinableThing.objects.for_user(delete_thing_permission, user))
        == owned_things
    )

    for permission in supported_permissions:
        assert set(JoinableThing.objects.for_user(permission, superuser)) == set(things)
        assert set(JoinableThing.objects.for_user(permission, AnonymousUser())) == set()


@hypothesis.given(st.text())
def test_joinable_for_user_with_invalid_permission(
    django_executor: Any, permission: str
):
    hypothesis.assume(permission not in supported_permissions)
    user = User(username="test")
    with pytest.raises(ValueError, match="unsupported permission"):
        JoinableThing.objects.for_user(permission, user)
