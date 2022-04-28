from typing import Optional

import strawberry
from django.db import models

from tumpara import api
from tumpara.accounts import api as accounts_api

from .models import JoinableThing


@strawberry.type
class JoinableThingNode(accounts_api.JoinableNode[JoinableThing], fields=[]):
    pass


@strawberry.type
class JoinableThingEdge(api.Edge[JoinableThingNode]):
    node: JoinableThingNode


@strawberry.type
class JoinableThingConnection(
    api.DjangoConnection[JoinableThingNode, JoinableThing],
    name="joinable thing",
    pluralized_name="joinable things",
):
    edges: list[Optional[JoinableThingEdge]]
    nodes: list[Optional[JoinableThingNode]]


@api.schema.query
class _:
    joinable_things: Optional[
        JoinableThingConnection
    ] = api.DjangoConnectionField()  # type: ignore
