import dataclasses
from typing import Optional

import pytest
import strawberry

from tumpara import api

from .models import Other, Thing


def test_django_node_wrong_initialization() -> None:
    with pytest.raises(TypeError, match="Django model"):

        class ThingNodeA(api.DjangoNode):
            pass

    with pytest.raises(TypeError, match="fields"):

        class ThingNodeB(api.DjangoNode):
            obj: strawberry.Private[Thing]

    with pytest.raises(TypeError, match="strings"):

        class ThingNodeC(api.DjangoNode, fields=[None]):
            obj: strawberry.Private[Thing]


def test_django_node_basic_creating() -> None:
    """``from_obj`` works as expected."""

    @strawberry.type
    class ThingNode(api.DjangoNode, fields=["foo", "bar"]):
        obj: strawberry.Private[Thing]

    assert set(ThingNode._get_field_names()) == {"pk", "foo", "bar"}

    thing = Thing(foo="foo", bar=14)
    node = ThingNode(obj=thing)
    assert node.foo == "foo"
    assert node.bar == 14


def test_django_node_related_fields() -> None:
    """``from_obj`` successfully resolves related fields."""

    @strawberry.type
    class OtherNode(api.DjangoNode, fields=["baz"]):
        obj: strawberry.Private[Other]

    @strawberry.type
    class ThingNode(api.DjangoNode, fields=["foo", "other"]):
        obj: strawberry.Private[Thing]
        other: Optional[OtherNode] = dataclasses.field(init=False)

    assert set(OtherNode._get_field_names()) == {"pk", "baz"}
    assert set(ThingNode._get_field_names()) == {"pk", "foo", "other"}

    thing = Thing(foo="outer", other=Other(baz=1.4))
    node = ThingNode(obj=thing)
    assert node.foo == "outer"
    assert node.other is not None
    assert node.other.baz == 1.4

    thing = Thing(foo="foo", other=None)
    node = ThingNode(obj=thing)
    assert node.foo == "foo"
    assert node.other is None
