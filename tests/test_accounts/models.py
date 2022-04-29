from django.db import models

from tumpara.accounts import models as accounts_models
from tumpara.accounts.models import JoinableQueryset

JoinableThingManager = models.Manager.from_queryset(JoinableQueryset)


class JoinableThing(accounts_models.Joinable):
    objects = JoinableThingManager()
