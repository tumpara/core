from collections.abc import Generator
from typing import Any

import pytest

from tumpara.utils import clean_storages, exiftool

from .utils import DjangoHypothesisExecutor

__all__ = ["django_executor"]


@pytest.fixture(scope="function")
def django_executor(
    django_db_setup: Any,  # pylint: disable=unused-argument
    django_db_blocker: Any,  # pylint: disable=unused-argument
) -> DjangoHypothesisExecutor:
    """This fixture enables a Hypothesis executor that will take care of any
    Django-related things (such as the database) that need to be cleared out in
    between individual test runs.

    Add this as the first fixture to a test. There is no need to use
    ``pytest.mark.django_db``, because that will only clear database transactions before
    and after the *entire* test and won't do anything in between individual Hypothesis
    runs. Instead, do this:

    .. code-block:: python

        @hypothesis.given(st.integers())
        def test_something(django_executor: Any, value: int) -> None:
            # Do something with the database...
    """
    return DjangoHypothesisExecutor()


@pytest.fixture(autouse=True)
def auto_clean_storages() -> Generator[None, None, None]:
    yield
    clean_storages()


@pytest.fixture(autouse=True)
def auto_stop_exiftool() -> Generator[None, None, None]:
    yield
    exiftool.stop_exiftool()
