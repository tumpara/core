from typing import Any

import django.test
from pytest_django.plugin import _blocking_manager as django_db_blocking_manager


class DjangoHypothesisExecutor:
    """Hypothesis executor that takes care of Django database transactions between
    runs.

    See also :func:`tumpara.testing.fixtures.django_executor`.
    """

    def __init__(self) -> None:
        self.test_case = django.test.TestCase(methodName="__init__")

    def setup_example(self, *args: Any, **kwargs: Any) -> None:
        django_db_blocking_manager.unblock()
        self.test_case._pre_setup()  # type: ignore

    def teardown_example(self, *args: Any, **kwargs: Any) -> None:
        self.test_case._post_teardown()  # type: ignore
        django_db_blocking_manager.restore()
