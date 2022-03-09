from __future__ import annotations

from functools import partial

from django.db import models
from django.utils import crypto, timezone
from django.utils.translation import gettext_lazy as _

from tumpara.accounts import models as accounts_models


class TokenQueryset(models.QuerySet["Token"]):
    def filter_valid(self) -> TokenQueryset:
        """Return a new queryset that only contains currently valid tokens."""
        return self.filter(
            models.Q(expiry_timestamp__isnull=True)
            | models.Q(expiry_timestamp__gt=timezone.now())
        )


TokenManager = models.Manager.from_queryset(TokenQueryset)


class Token(models.Model):
    """Token that allows access to the API as a specific user."""

    key = models.CharField(
        _("key"),
        max_length=32,
        primary_key=True,
        default=partial(crypto.get_random_string, 32),
    )
    user = models.ForeignKey(
        accounts_models.User,
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
