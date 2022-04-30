from django.db import models

from tumpara.accounts.models import Joinable, JoinableQueryset

JoinableThingManager = models.Manager.from_queryset(JoinableQueryset)


class JoinableThing(Joinable):
    objects = JoinableThingManager()
