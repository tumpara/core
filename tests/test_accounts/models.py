from django.db import models

from tumpara.accounts.models import Joinable, JoinableQuerySet

JoinableThingManager = models.Manager.from_queryset(JoinableQuerySet)


class JoinableThing(Joinable):
    objects = JoinableThingManager()
