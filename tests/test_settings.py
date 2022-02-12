from typing import Optional

import django.core.exceptions
import hypothesis
import pytest

from . import settings


def test_string_or_none():
    assert settings.string_or_none("hi") == "hi"
    assert settings.string_or_none("") is None
    assert settings.string_or_none(None) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("yes", True),
        ("YES", True),
        ("1", True),
        ("true", True),
        ("ON", True),
        ("no", False),
        ("0", False),
        ("FALse", False),
        ("ofF", False),
        ("no idea", None),
        ("something", None),
    ],
)
def test_parse_env_boolean(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: Optional[bool]
):
    monkeypatch.setenv("TESTING_VARIABLE", value)
    if expected is not None:
        assert settings.parse_env("TESTING_VARIABLE", None, bool) is expected
    else:
        with pytest.raises(django.core.exceptions.ImproperlyConfigured):
            settings.parse_env("TESTING_VARIABLE", None, bool)


def test_parse_env_defaults():
    assert settings.parse_env("TESTING_VARIABLE", "hello", bool) == "hello"


def test_parse_env_cast(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TESTING_VARIABLE", "14")
    assert settings.parse_env("TESTING_VARIABLE", "hello", int) == 14
    monkeypatch.setenv("TESTING_VARIABLE", "abc")
    with pytest.raises(django.core.exceptions.ImproperlyConfigured):
        settings.parse_env("TESTING_VARIABLE", "hello", int)
