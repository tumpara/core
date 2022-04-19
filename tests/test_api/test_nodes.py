from typing import Optional

import pytest
import strawberry

from tumpara import api

from .models import Other, Thing


def test_django_node_wrong_initialization():
    with pytest.raises(AssertionError, match="must be initialized with a Django model"):

        class ThingNode(api.DjangoNode[None]):
            pass

    with pytest.raises(TypeError, match="fields"):

        class ThingNode(api.DjangoNode[Thing]):
            pass

    with pytest.raises(TypeError, match="strings"):

        class ThingNode(api.DjangoNode[Thing], fields=[None]):
            pass


def test_django_node_basic_creating():
    """``from_obj`` works as expected."""

    @strawberry.type
    class ThingNode(api.DjangoNode[Thing], fields=["foo", "bar"]):
        pass

    assert set(ThingNode.field_names()) == {"pk", "foo", "bar"}

    thing = Thing(foo="foo", bar=14)
    node = ThingNode.from_obj(thing)
    assert node.foo == "foo"
    assert node.bar == 14


def test_django_node_related_fields():
    """``from_obj`` successfully resolves related fields."""

    @strawberry.type
    class OtherNode(api.DjangoNode[Other], fields=["baz"]):
        pass

    @strawberry.type
    class ThingNode(api.DjangoNode[Thing], fields=["foo", "other"]):
        other: Optional[OtherNode]

    assert set(OtherNode.field_names()) == {"pk", "baz"}
    assert set(ThingNode.field_names()) == {"pk", "foo", "other"}

    thing = Thing(foo="outer", other=Other(baz=1.4))
    node = ThingNode.from_obj(thing)
    assert node.foo == "outer"
    assert node.other.baz == 1.4

    thing = Thing(foo="foo", other=None)
    node = ThingNode.from_obj(thing)
    assert node.foo == "foo"
    assert node.other is None
