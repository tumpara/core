from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Collection, Generic, Optional, TypeVar, cast

import django.contrib.auth
import django.contrib.auth.validators
from django.contrib.auth import models as auth_models
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes import fields as contenttypes_fields
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .utils import build_permission_name

if TYPE_CHECKING:
    from .backends import JoinablesBackend  # noqa: F401

__all__ = ["AnonymousUser", "User", "Joinable", "UserMembership"]


class UserManager(auth_models.UserManager["User"]):
    def create_superuser(
        self,
        username: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        **extra_fields: Any,
    ) -> User:
        # This override removes the is_staff option.
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return super().create_superuser(username, email, password, **extra_fields)


class User(auth_models.AbstractBaseUser, auth_models.PermissionsMixin):
    """The main user model. Each account receives an instance of this type."""

    username = models.CharField(
        _("identifier"),
        unique=True,
        max_length=150,
        validators=[django.contrib.auth.validators.UnicodeUsernameValidator()],
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
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __init__(self, *args: Any, **kwargs: Any):
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

        # Go through all the backends with the set of keyed permissions and check
        # them.
        keyed_permissions = defaultdict[str, set[str]](set)
        for permission in perm_list:
            if "__" not in permission:
                continue
            permission_name, key = permission.split("__")
            keyed_permissions[permission_name].add(key)

        if len(keyed_permissions) > 0 and obj is not None:
            raise RuntimeError(
                "keyed permissions with a single object are not supported"
            )

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
    object_pk = models.PositiveIntegerField()
    content_object = contenttypes_fields.GenericForeignKey("content_type", "object_pk")

    class Meta:
        verbose_name = _("user membership")
        verbose_name_plural = _("user memberships")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "content_type", "object_pk"],
                name="user_object_membership_unique",
            ),
        ]


class JoinableQueryset(models.QuerySet["Joinable"]):
    def for_user(self, permission: str, user: User | AnonymousUser) -> JoinableQueryset:
        """Narrow down the queryset to only return elements where the given user has
        a specific permission."""
        if not user.is_authenticated or not user.is_active:
            return self.none()
        if user.is_superuser:
            return self

        if permission in (
            build_permission_name(self.model, "change"),
            build_permission_name(self.model, "delete"),
        ):
            return self.filter(
                user_memberships__user=user, user_memberships__is_owner=True
            )
        elif permission == build_permission_name(self.model, "view"):
            membership_queryset = UserMembership.objects.filter(
                user=user,
                content_type=ContentType.objects.get_for_model(self.model),
                object_pk=models.OuterRef("pk"),
            )
            return self.filter(models.Exists(membership_queryset))
        else:
            raise ValueError(f"unsupported permission: {permission}")


JoinableManager = models.Manager.from_queryset(JoinableQueryset)


class Joinable(models.Model):
    """Base class to indicate that users should be able to become members of a model."""

    user_memberships = contenttypes_fields.GenericRelation(
        UserMembership, "object_pk", "content_type"
    )

    objects = JoinableManager()

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
            object_pk=self.pk,
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
            object_pk=self.pk,
        ).delete()

    def clear_memberships(self) -> None:
        """Remove all memberships. After this, only superusers will have access."""
        content_type = ContentType.objects.get_for_model(self, for_concrete_model=True)
        UserMembership.objects.filter(
            content_type=content_type,
            object_pk=self.pk,
        ).delete()
