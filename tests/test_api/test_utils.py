from typing import Optional, Union

import pytest

from tumpara.api import utils


def test_is_optional():
    assert utils.is_type_optional(Optional[str])
    assert utils.is_type_optional(int | None)
    assert utils.is_type_optional(None | float)
    assert utils.is_type_optional(Union[bytes, None])
    assert utils.is_type_optional(Union[None, complex])
    assert utils.is_type_optional(Optional[int | float])
    assert utils.is_type_optional(int | float | complex | None)
    assert not utils.is_type_optional(str)
    assert not utils.is_type_optional(float | int)


def test_extract_optional_type():
    assert utils.extract_optional_type(Optional[str]) is str
    assert utils.extract_optional_type(int | None) is int
    assert utils.extract_optional_type(None | float) is float
    assert utils.extract_optional_type(Union[bytes, None]) is bytes
    assert utils.extract_optional_type(Union[None, complex]) is complex
    assert utils.extract_optional_type(Optional[int | float]) == int | float
    assert (
        utils.extract_optional_type(int | float | complex | None)
        == int | float | complex
    )

    with pytest.raises(TypeError):
        utils.extract_optional_type(str)
    with pytest.raises(TypeError):
        utils.extract_optional_type(float | int)
