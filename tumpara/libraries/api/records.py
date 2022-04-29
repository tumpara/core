import enum
from typing import Optional

import strawberry
from django import forms

from tumpara import api
from tumpara.accounts import api as accounts_api
from tumpara.accounts import models as accounts_models
from tumpara.libraries import models as libraries_models
from tumpara.libraries import storage

from .libraries import LibraryNode, LibraryVisibility


@strawberry.enum
class RecordVisibility(LibraryVisibility):
    INHERIT = libraries_models.Visibility.INHERIT


@strawberry.interface(name="Record")
class RecordNode(
    api.DjangoNode[libraries_models.Record], fields=["library", "visibility"]
):
    library: Optional[LibraryNode]
    visibility: RecordVisibility
