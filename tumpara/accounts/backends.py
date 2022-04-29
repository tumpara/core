from typing import Optional, cast

from django.contrib.auth.backends import BaseBackend
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import models

from .models import AnonymousUser, Joinable, User, UserMembership
from .utils import build_permission_name


class UserViewingBackend(BaseBackend):
    """User backend that allows logged-in uses to view other profiles and change their
    own."""

    def get_user_permissions(
        self,
        user_obj: models.Model | AnonymousUser,
        obj: Optional[models.Model] = None,
    ) -> set[str]:
        if (
            not cast(User, user_obj).is_active
            or not cast(User, user_obj).is_authenticated
        ):
            return set()
        assert isinstance(user_obj, User)

        permissions = set[str]()

        if isinstance(obj, User):
            permissions = {build_permission_name(obj, "view")}
            if user_obj == obj:
                permissions.add(build_permission_name(obj, "change"))
            if user_obj.is_superuser:
                permissions.add(build_permission_name(obj, "delete"))
        elif obj is None:
            permissions = {build_permission_name(User, "view")}
            if user_obj.is_superuser:
                permissions.add(build_permission_name(User, "add"))
                permissions.add(build_permission_name(User, "change"))
                permissions.add(build_permission_name(User, "delete"))
        else:
            return super().get_user_permissions(user_obj, obj)

        return permissions


class JoinablesBackend(BaseBackend):
    """User backend that supports querying for permissions based on memberships added
    by a :class:`tumpara.accounts.models.Joinable`.

    Django's default auth module provides permissions for viewing, changing and
    deleting each model. Their names are built using the corresponding app and model
    names, for example ``accounts.view_user``, ``accounts.change_user`` and
    ``accounts.delete_user``. When using :meth:``User.has_perm`` in combination with
    an object, these queries will by answered according to the user's membership status.
    If you don't provide an object, they will use the Django-default system with
    permission objects.

    To find out if a user has access to an object, use one of the following two calls.
    The latter is more generic, but if you now the name of the permission directly you
    can use that as well:

        >>> some_user.has_perm("libraries.view_library", the_library)
        >>> some_user.has_perm(the_library.change_permission_name, the_library)

    Further, you can use a special permission name syntax for checking multiple objects
    at once. These names should be passed to :meth:`User.has_perms`, without specifying
    an object. Here is an example:

        >>> some_user.has_perms(
        ...     f"libraries.view_library__{first.pk}",
        ...     f"libraries.change_library__{second.pk}",
        ... )

    The above call will return ``True`` if and only if ``some_user`` has view access to
    the first and change access to the second library. In general, the three permission
    types (view, change and delete) mentioned above are supported. Build the correct
    permission string by joining the actual permission's name (which is returned by
    :attr:`tumpara.accounts.models.Joinable.change_permission_name` and the like) with
    the object's primary key using a double underscore.

    .. note::
        These special permissions only work when using ``.has_perms()`` (note the *s*).
        When checking permissions on a single object, use ``.has_perm()`` with the
        normal permission name and pass the object -- which is the syntax preferred by
        Django.
    """

    def get_user_permissions(
        self, user_obj: models.Model | AnonymousUser, obj: Optional[models.Model] = None
    ) -> set[str]:
        # The Joinable instance check isn't actually required for this to function, but
        # it improves performance.
        if obj is None or not isinstance(obj, Joinable):
            return super().get_user_permissions(user_obj, obj)
        if (
            not cast(User, user_obj).is_active
            or not cast(User, user_obj).is_authenticated
        ):
            return set()
        assert isinstance(
            user_obj, User
        ), "got unknown user model type for permission check"

        try:
            content_type = ContentType.objects.get_for_model(
                obj, for_concrete_model=True
            )
            membership = user_obj.memberships.get(
                content_type=content_type, object_pk=obj.pk
            )

            permissions = {build_permission_name(obj, "view")}
            if membership.is_owner:
                permissions.add(build_permission_name(obj, "change"))
                permissions.add(build_permission_name(obj, "delete"))
            return permissions
        except UserMembership.DoesNotExist:
            return set()

    def get_all_permissions(
        self, user_obj: models.Model | AnonymousUser, obj: Optional[models.Model] = None
    ) -> set[str]:
        if obj is None:
            return super().get_user_permissions(user_obj, obj)
        return self.get_user_permissions(user_obj, obj)

    def has_keyed_permissions(
        self,
        user_obj: User | AnonymousUser,
        permission_name: str,
        keys: set[str],
    ) -> bool:
        # This backend doesn't support any permissions on anonymous users.
        if not user_obj.is_authenticated:
            return False
        assert isinstance(user_obj, User)

        # Extract the app label, action and model name out of a permission string
        # something like 'libraries.change_library'. Skip invalid permissions.
        if "." not in permission_name:
            return False
        app_label, permission_codename = permission_name.split(".", 1)
        if "_" not in permission_codename:
            return False
        action, model_name = permission_codename.split("_", 1)
        if action not in ("view", "change", "delete"):
            return False

        query = models.Q(
            content_type__app_label=app_label,
            content_type__model=model_name,
            object_pk__in=keys,
        )
        if action in ("change", "delete"):
            query &= models.Q(is_owner=True)

        if user_obj.memberships.filter(query).count() == len(keys):
            return True
        else:
            raise PermissionDenied
