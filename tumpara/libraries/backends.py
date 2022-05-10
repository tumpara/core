from typing import Optional, cast

from django.contrib.auth.backends import BaseBackend
from django.db import models

from tumpara.accounts.models import AnonymousUser, User
from tumpara.accounts.utils import build_permission_name

from .models import Library, Record


class LibraryCreatingBackend(BaseBackend):
    """Permission backend that allows all logged-in users to create libraries."""

    def get_user_permissions(
        self,
        user_obj: models.Model | AnonymousUser,
        obj: Optional[models.Model] = None,
    ) -> set[str]:
        if (
            obj is None
            or not isinstance(obj, Library)
            or not cast(User, user_obj).is_active
            or not cast(User, user_obj).is_authenticated
        ):
            return set()

        if obj._state.adding:
            return {"libraries.add_library"}
        else:
            return {}


class LibraryRecordsBackend(BaseBackend):
    """User backend for library records."""

    def get_user_permissions(
        self,
        user_obj: models.Model | AnonymousUser,
        obj: Optional[models.Model] = None,
    ) -> set[str]:
        if (
            obj is None
            or not isinstance(obj, Record)
            or not cast(User, user_obj).is_active
            or not cast(User, user_obj).is_authenticated
        ):
            return set()
        assert isinstance(user_obj, User)

        library_permissions = user_obj.get_all_permissions(obj.library)
        permissions = set[str]()

        if "libraries.view_library" in library_permissions:
            permissions.add(build_permission_name(obj, "view"))
        if "libraries.change_library" in library_permissions:
            # The deletion permission on the library doesn't allow us to do anything
            # with individual records.
            permissions.add(build_permission_name(obj, "add"))
            permissions.add(build_permission_name(obj, "change"))
            permissions.add(build_permission_name(obj, "delete"))

        return permissions
