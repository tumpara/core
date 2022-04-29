import enum
from typing import Optional

import strawberry
from django import forms

from tumpara import api
from tumpara.accounts import api as accounts_api
from tumpara.accounts import models as accounts_models
from tumpara.libraries import models as libraries_models
from tumpara.libraries import storage


@strawberry.interface(name="Record")
class RecordNode(api.DjangoNode[libraries_models.Record]):
    pass
