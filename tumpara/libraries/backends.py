from typing import Optional, cast

from django.contrib.auth.backends import BaseBackend
from django.db import models

from tumpara.accounts import models as accounts_models
from tumpara.accounts.utils import build_permission_name

from .models import Record


class LibraryRecordsBackend(BaseBackend):
    """User backend for library records."""

    def get_user_permissions(
        self,
        user_obj: models.Model | accounts_models.AnonymousUser,
        obj: Optional[models.Model] = None,
    ) -> set[str]:
        if (
            obj is None
            or not isinstance(obj, Record)
            or not cast(accounts_models.User, user_obj).is_active
            or not cast(accounts_models.User, user_obj).is_authenticated
        ):
            return set()
        assert isinstance(user_obj, accounts_models.User)

        library_permissions = user_obj.get_all_permissions(obj.library)
        permissions = set[str]()

        if "libraries.view_library" in library_permissions:
            permissions.add(build_permission_name(obj, "view"))
        if "libraries.change_library" in library_permissions:
            # The deletion permission on the library doesn't allow us to do anything
            # with individual records.
            permissions.add(build_permission_name(obj, "change"))
            permissions.add(build_permission_name(obj, "delete"))

        return permissions
