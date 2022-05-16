from typing import Optional, cast

from django.contrib.auth.backends import BaseBackend
from django.db import models

from tumpara.accounts.models import AnonymousUser, User

from .models import Album


class AlbumCreatingBackend(BaseBackend):
    """Permission backend that allows all logged-in users to create albums."""

    def get_user_permissions(
        self,
        user_obj: models.Model | AnonymousUser,
        obj: Optional[models.Model] = None,
    ) -> set[str]:
        if (
            obj is None
            or not isinstance(obj, Album)
            or not cast(User, user_obj).is_active
            or not cast(User, user_obj).is_authenticated
        ):
            return set()

        if obj._state.adding:
            return {"gallery.add_album"}
        else:
            return set()
