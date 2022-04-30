import pytest

from tumpara.accounts.models import AnonymousUser
from tumpara.libraries.models import Library

from ..test_accounts.utils import user_dataset  # noqa: F401
from ..test_accounts.utils import UserDataset
from .models import GenericHandler
from .test_event_handling import library  # noqa: F401


@pytest.mark.django_db
def test_record_permissions(user_dataset: UserDataset, library: Library) -> None:
    """Permissions for records are inherited from the library."""
    bob, carl, dave, *_ = user_dataset

    record = GenericHandler.objects.create(library=library, content=b"hi")

    anonymous = AnonymousUser()
    assert not anonymous.has_perm("test_libraries.view_generichandler", record)
    assert not anonymous.has_perm("test_libraries.change_generichandler", record)
    assert not anonymous.has_perm("test_libraries.delete_generichandler", record)

    assert not bob.has_perm("test_libraries.view_generichandler", record)
    assert not bob.has_perm("test_libraries.change_generichandler", record)
    assert not bob.has_perm("test_libraries.delete_generichandler", record)

    library.add_membership(carl)
    assert carl.has_perm("test_libraries.view_generichandler", record)
    assert not carl.has_perm("test_libraries.change_generichandler", record)
    assert not carl.has_perm("test_libraries.delete_generichandler", record)

    library.add_membership(dave, owner=True)
    assert dave.has_perm("test_libraries.view_generichandler", record)
    assert dave.has_perm("test_libraries.change_generichandler", record)
    assert dave.has_perm("test_libraries.delete_generichandler", record)
