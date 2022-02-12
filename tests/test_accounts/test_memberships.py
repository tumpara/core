import pytest

from tumpara.accounts.models import AnonymousUser, User

from .models import JoinableThing


@pytest.mark.django_db
def test_regular_user_permissions() -> None:
    """Permission checks on :class:`User` instances work as expected when adding them
    to joinables."""
    bob = User.objects.create_user("bob")
    carl = User.objects.create_user("carl")
    dave = User.objects.create_user("dave")
    thing = JoinableThing.objects.create()

    for user in (bob, carl, dave):
        # Make sure the permissions aren't set globally first. That way we are actually
        # testing the per-object permissions below.
        assert not user.has_perm(thing.change_permission_name)
        assert not user.has_perm(thing.delete_permission_name)
        assert not user.has_perm(thing.view_permission_name)

        assert not user.has_perm(thing.change_permission_name, thing)
        assert not user.has_perm(thing.delete_permission_name, thing)
        assert not user.has_perm(thing.view_permission_name, thing)

    thing.add_membership(carl)
    thing.add_membership(dave, owner=True)

    assert not bob.has_perm(thing.change_permission_name, thing)
    assert not bob.has_perm(thing.delete_permission_name, thing)
    assert not bob.has_perm(thing.view_permission_name, thing)

    assert not carl.has_perm(thing.change_permission_name, thing)
    assert not carl.has_perm(thing.delete_permission_name, thing)
    assert carl.has_perm(thing.view_permission_name, thing)

    assert dave.has_perm(thing.change_permission_name, thing)
    assert dave.has_perm(thing.delete_permission_name, thing)
    assert dave.has_perm(thing.view_permission_name, thing)


@pytest.mark.django_db
def test_regular_user_bulk_permissions() -> None:
    """Bulk permission check work in the same way as regular permission checks."""
    first = JoinableThing.objects.create()
    second = JoinableThing.objects.create()

    bob = User.objects.create_user("bob")  # No member
    carl = User.objects.create_user("carl")  # First: member, Second: nothing
    dave = User.objects.create_user("dave")  # First: member, Second: member
    frank = User.objects.create_user("frank")  # First: owner, Second: nothing
    jerry = User.objects.create_user("jerry")  # First: owner, Second: member
    kevin = User.objects.create_user("kevin")  # First: owner, Second: owner

    for user in (bob, carl, dave, frank, jerry, kevin):
        assert not user.has_perms([first.change_permission_name], first)
        assert not user.has_perms([first.delete_permission_name], first)
        assert not user.has_perms([first.view_permission_name], first)

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
        assert not user.has_perms([first.change_permission_name])
        assert not user.has_perms([first.delete_permission_name])
        assert not user.has_perms([first.view_permission_name])

    change_first = f"{first.change_permission_name}__{first.pk}"
    delete_first = f"{first.delete_permission_name}__{first.pk}"
    view_first = f"{first.view_permission_name}__{first.pk}"
    change_second = f"{second.change_permission_name}__{second.pk}"
    delete_second = f"{second.delete_permission_name}__{second.pk}"
    view_second = f"{second.view_permission_name}__{second.pk}"

    assert not bob.has_perms([change_first])
    assert not bob.has_perms([delete_first, change_second])
    assert not bob.has_perms([view_first])
    assert not bob.has_perms([first.view_permission_name], first)

    assert carl.has_perms([view_first])
    assert carl.has_perms([first.view_permission_name], first)
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
def test_superuser_permissions() -> None:
    """Superusers have full access to joinables."""
    bob = User.objects.create_superuser("bob", None, None)
    thing = JoinableThing.objects.create()

    assert bob.has_perm(thing.change_permission_name)
    assert bob.has_perm(thing.delete_permission_name)
    assert bob.has_perm(thing.view_permission_name)
    assert bob.has_perm(thing.change_permission_name, thing)
    assert bob.has_perm(thing.delete_permission_name, thing)
    assert bob.has_perm(thing.view_permission_name, thing)


@pytest.mark.django_db
def test_superuser_bulk_permissions() -> None:
    """Superusers have full access when bulk checking permissions."""
    bob = User.objects.create_superuser("bob", None, None)
    first = JoinableThing.objects.create()
    second = JoinableThing.objects.create()

    change_first = f"{first.change_permission_name}__{first.pk}"
    delete_first = f"{first.delete_permission_name}__{first.pk}"
    view_first = f"{first.view_permission_name}__{first.pk}"
    change_second = f"{second.change_permission_name}__{second.pk}"
    delete_second = f"{second.delete_permission_name}__{second.pk}"
    view_second = f"{second.view_permission_name}__{second.pk}"

    assert bob.has_perms(
        [
            change_first,
            delete_first,
            view_first,
            change_second,
            delete_second,
            view_second,
        ]
    )
    assert bob.has_perms([change_first, view_first, change_second, view_second])
    assert bob.has_perms([first.change_permission_name], first)
    assert bob.has_perms([second.view_permission_name], second)


@pytest.mark.django_db
def test_anonymous_user_permissions() -> None:
    """Anonymous users have no access to joinables."""
    bob = AnonymousUser()
    thing = JoinableThing.objects.create()

    assert not bob.has_perm(thing.change_permission_name)
    assert not bob.has_perm(thing.delete_permission_name)
    assert not bob.has_perm(thing.view_permission_name)
    assert not bob.has_perm(thing.change_permission_name, thing)
    assert not bob.has_perm(thing.delete_permission_name, thing)
    assert not bob.has_perm(thing.view_permission_name, thing)


@pytest.mark.django_db
def test_anonymous_bulk_permissions() -> None:
    """Anonymous users have no access when checking permissions in bulk."""
    bob = AnonymousUser()
    first = JoinableThing.objects.create()
    second = JoinableThing.objects.create()

    change_first = f"{first.change_permission_name}__{first.pk}"
    delete_first = f"{first.delete_permission_name}__{first.pk}"
    view_first = f"{first.view_permission_name}__{first.pk}"
    change_second = f"{second.change_permission_name}__{second.pk}"
    delete_second = f"{second.delete_permission_name}__{second.pk}"
    view_second = f"{second.view_permission_name}__{second.pk}"

    assert not bob.has_perms(
        [
            change_first,
            delete_first,
            view_first,
            change_second,
            delete_second,
            view_second,
        ]
    )
    assert not bob.has_perms([change_first, view_first, change_second, view_second])
    assert not bob.has_perms([first.change_permission_name], first)
    assert not bob.has_perms([second.view_permission_name], second)
