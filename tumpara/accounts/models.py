from collections import defaultdict
from typing import TYPE_CHECKING, Any, Collection, Optional, cast, final

import django.contrib.auth
import django.contrib.auth.validators
import django.contrib.contenttypes.fields
from django.contrib.auth import models as auth_models
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils.translation import gettext_lazy as _

from .utils import build_permission_name

if TYPE_CHECKING:
    from .backends import JoinablesBackend

__all__ = ["AnonymousUser", "User", "Joinable", "UserMembership"]


class UserManager(auth_models.UserManager["User"]):
    # The following methods are overridden because the argument is initially named
    # 'username' but that field is called 'login_name' in our user model.

    def create_user(  # type: ignore
        self,
        login_name: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        **extra_fields: Any,
    ):
        return super().create_user(login_name, email, password, **extra_fields)

    def create_superuser(  # type: ignore
        self,
        login_name: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        **extra_fields: Any,
    ):
        return super().create_user(login_name, email, password, **extra_fields)


class User(auth_models.AbstractBaseUser, auth_models.PermissionsMixin):
    """The main user model. Each account receives an instance of this type."""

    login_validator = django.contrib.auth.validators.UnicodeUsernameValidator()
    login_name = models.CharField(
        _("identifier"),
        unique=True,
        max_length=150,
        validators=[login_validator],
        help_text=_(
            "Username used for logging in. This must have 150 characters or fewer and "
            "may only contain letters, digits and these characters: @ . + - _"
        ),
    )

    full_name = models.CharField(
        _("full name"),
        blank=True,
        max_length=150,
        help_text=_("Full name of the account owner."),
    )
    short_name = models.CharField(
        _("display name"),
        blank=True,
        max_length=150,
        help_text=_(
            "Short name this user should be referred to with. In most cases, this will "
            "be the user's first name, but they may something different (like a "
            "nickname) as well. If this is blank, clients should default to the full "
            "name."
        ),
    )
    email = models.EmailField(_("email address"), blank=True)

    is_active = models.BooleanField(
        _("active status"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. Unselect this "
            "instead of deleting accounts."
        ),
    )

    preferences = models.JSONField(
        null=True,
        verbose_name=_("preferences"),
        help_text=_(
            "Storage space arbitrary settings / preference values that can be used by "
            "clients."
        ),
    )

    objects = UserManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "login_name"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __init__(
        self,
        *args: Any,
        username: Optional[str] = None,
        **kwargs: Any,
    ):
        # Map the 'username' option to our login_name field because the default
        # UserManager implementation (which we would like to keep) expects the field to
        # be named that way. This might also help in other edge cases that assume the
        # name of the username field.
        if username is not None:
            kwargs.setdefault("login_name", username)
        # We don't have the notion of 'staff users'.
        if "is_staff" in kwargs:
            del kwargs["is_staff"]
        super().__init__(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def has_perms(
        self,
        perm_list: Collection[str],
        obj: Optional[models.Model | AnonymousUser] = None,
    ) -> bool:
        """Check if the user has all the specified permissions.

        This implementation uses the authentication backends, if available. It also
        supports a special syntax for providing permissions: permissions can optionally
        have a *key*, delimited by a double underscore. These keyed permissions will be
        resolved by backends that have a ``has_keyed_permissions`` method.

        Using keyed permissions is an alternative to using objects which have two
        advantages:

        1. They work in bulk
        2. There is no need to actually resolve the individual objects, as primary keys
          are appended to the permission string.

        See :class:`JoinablesBackend` for some examples on how they are used.
        """
        assert len(perm_list) > 0

        if self.is_active and self.is_superuser:
            return True

        normal_permissions = set(perm for perm in perm_list if "__" not in perm)
        if not super().has_perms(normal_permissions, obj):
            return False

        # Go through all the backends with the set of special permissions and check
        # them.
        keyed_permissions = defaultdict[str, set[str]](set)
        for permission in perm_list:
            if "__" not in permission:
                continue
            permission_name, key = permission.split("__")
            keyed_permissions[permission_name].add(key)

        if len(keyed_permissions) > 0 and obj is not None:
            raise RuntimeError("keyed permissions with an object are not supported")

        for permission_name, keys in keyed_permissions.items():
            passed = False
            for backend in django.contrib.auth.get_backends():
                if not hasattr(backend, "has_keyed_permissions"):
                    continue
                try:
                    if cast("JoinablesBackend", backend).has_keyed_permissions(
                        self, permission_name, keys
                    ):
                        passed = True
                        break
                except PermissionDenied:
                    return False
            if not passed:
                return False

        # Since each permission passed individually (either in the normal_permissions
        # section or while looping through the keyed permissions), we are good to go
        # here.
        return True


class Joinable(models.Model):
    """Base class to indicate that users should be able to become members of a model."""

    class Meta:
        abstract = True

    def add_membership(self, user: User, owner: bool = False) -> None:
        """Add the given user as a member. If a membership already exists, it will
        be created.

        :param user: The user to add as a new or existing member.
        :param owner: Whether the user should be an owner (and have write permissions).
        """
        content_type = ContentType.objects.get_for_model(self, for_concrete_model=True)
        UserMembership.objects.update_or_create(
            user=user,
            content_type=content_type,
            object_id=self.pk,
            defaults=dict(is_owner=owner),
        )

    def remove_membership(self, user: User) -> None:
        """Remove a given user's membership, if it exists.

        :param user: The user to remove.
        """
        content_type = ContentType.objects.get_for_model(self, for_concrete_model=True)
        UserMembership.objects.filter(
            user=user,
            content_type=content_type,
            object_id=self.pk,
        ).delete()

    def clear_memberships(self) -> None:
        """Remove all memberships. After this, only superusers will have access."""
        content_type = ContentType.objects.get_for_model(self, for_concrete_model=True)
        UserMembership.objects.filter(
            content_type=content_type,
            object_id=self.pk,
        ).delete()

    @final
    @property
    def change_permission_name(self) -> str:
        """Helper to quickly access the name of the changing permission.

        This is not intended to be overridden, as these names are hard-coded into the
        Django auth module.
        """
        return build_permission_name(self, "change")

    @final
    @property
    def delete_permission_name(self) -> str:
        """Helper to quickly access the name of the deleting permission."""
        return build_permission_name(self, "delete")

    @final
    @property
    def view_permission_name(self) -> str:
        """Helper to quickly access the name of the viewing permission."""
        return build_permission_name(self, "view")


class AbstractMembership(models.Model):
    """Base class for all memberships."""

    is_owner = models.BooleanField(
        verbose_name=_("owner status"),
        help_text=_(
            "Designates that this membership has edit permissions on the object (for "
            "containers, they may add or remove)."
        ),
    )

    class Meta:
        abstract = True


class UserMembership(AbstractMembership):
    """Membership of a :class:`User` in some scope. The object that is referred to
    (which "hosts" the membership) should implement :class:`Joinable`."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="memberships",
        related_query_name="membership",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = django.contrib.contenttypes.fields.GenericForeignKey(
        "content_type", "object_id"
    )

    class Meta:
        verbose_name = _("user membership")
        verbose_name_plural = _("user memberships")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content_type", "object_id"],
                name="user_object_membership_unique",
            ),
        ]
