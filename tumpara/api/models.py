from __future__ import annotations

import functools
from typing import Any, Optional

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import crypto, timezone
from django.utils.translation import gettext_lazy as _

from tumpara.accounts.models import User

# These values are fixed. Don't change them if you don't want to break stuff!
TOKEN_PREFIX = "tumpara"
TOKEN_SEPARATOR = "_"
TOKEN_KEY_LENGTH = 12
TOKEN_SECRET_LENGTH = 40


class TokenQueryset(models.QuerySet["Token"]):
    def filter_valid(self) -> TokenQueryset:
        """Return a new queryset that only contains currently valid tokens."""
        return self.filter(
            models.Q(expiry_timestamp__isnull=True)
            | models.Q(expiry_timestamp__gt=timezone.now())
        )


TokenManagerBase = models.Manager.from_queryset(TokenQueryset)


class TokenManager(TokenManagerBase["Token"]):
    def generate_token(self, **kwargs: Any) -> tuple[Token, str]:
        """Generate a new token.

        This method returns a 2-tuple containing of the actual :class:`Token` object as
        well as the actual token string that should be used by clients. Note the string
        form is only available once and cannot be reproduced later.

        The client-facing token is a string that looks something like this:
        ``tumpara_U012TvnX20_oVaEfutEYA70hXP3PTAFrtjcQFF12Tpe``. It consists of three
        parts:

        - A constant prefix that identifies the token type. This will always be ``tumpara``.
        - The token's key, which is used to identify it.
        - A secret value that is encrypted like a password and cannot be retrieved from the database. This is used to verify the token's authenticity.

        Any additional keyword arguments will be passed along to the created model. Do
        not pass ``secret`` as it will be generated.
        """
        if "secret" in kwargs:
            raise ValueError("do not manually set the token secret")

        raw_secret = crypto.get_random_string(64)
        token = self.create(
            secret=make_password(raw_secret),
            **kwargs,
        )
        api_token = TOKEN_SEPARATOR.join((TOKEN_PREFIX, token.key, raw_secret))
        return token, api_token

    def check_token(self, api_token: str) -> Optional[Token]:
        """Check whether the given token string is valid.

        If so, the corresponding :class:`Token` object will be returned, or ``None``
        otherwise. The given string should be the client-facing token returned by
        :meth:`generate_token`.
        """
        try:
            prefix, key, raw_secret = api_token.strip().split(TOKEN_SEPARATOR)
        except ValueError:
            return None
        if prefix != TOKEN_PREFIX or len(key) != TOKEN_KEY_LENGTH:
            return None

        try:
            token = (
                self.get_queryset().prefetch_related("user").filter_valid().get(key=key)
            )
        except (Token.DoesNotExist, Token.MultipleObjectsReturned):
            return None

        def setter(new_raw_secret: str) -> None:
            token.secret = make_password(new_raw_secret)
            token.save(update_fields=["secret"])

        if not check_password(raw_secret, token.secret, setter):
            return None

        return token


class Token(models.Model):
    """Token that allows access to the API as a specific user."""

    key = models.CharField(
        _("key"),
        max_length=TOKEN_KEY_LENGTH,
        unique=True,
        default=functools.partial(crypto.get_random_string, TOKEN_KEY_LENGTH),
    )
    secret = models.CharField(_("secret"), max_length=128)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="api_tokens",
        related_query_name="api_token",
        verbose_name=_("user"),
        help_text=_(
            "The user connected to the token. Any actions will be performed in their "
            "name."
        ),
    )
    expiry_timestamp = models.DateTimeField(
        _("valid until"),
        null=True,
        help_text=_("The token will become invalid after this timestamp."),
    )

    name = models.CharField(
        _("name"),
        max_length=100,
        blank=True,
        help_text=_("Human-readable name for this token."),
    )

    creation_timestamp = models.DateTimeField(_("created at"), auto_now_add=True)
    usage_timestamp = models.DateTimeField(_("last used"), auto_now=True)

    objects = TokenManager()

    class Meta:
        verbose_name = _("API token")
        verbose_name_plural = _("API tokens")
