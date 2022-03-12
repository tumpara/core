from tumpara.accounts import models as accounts_models


class JoinableThing(accounts_models.Joinable):
    objects = accounts_models.JoinableManager()
