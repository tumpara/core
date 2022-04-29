from collections.abc import Callable
from typing import Any

import django.test
import hypothesis.stateful
import pytest
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


def state_machine(
    *,
    use_django_executor: bool = False,
) -> Callable[[type[hypothesis.stateful.RuleBasedStateMachine]], Callable[[], None]]:
    """Decorator for using Hypothesis state machines with the testing framework.

    Apply this to a subclass of :class:`hypothesis.stateful.RuleBasedStateMachine`, for
    example:

    .. code-block:: python

        import hypothesis.stateful
        from tumpara import testing

        @testing.state_machine()
        class test_something(hypothesis.stateful.RuleBasedStateMachine):
            ...

    :param use_django_executor: Whether to enable the django executor (see
        :func:`tumpara.testing.fixtures.django_executor`). Enable this if you need
        database access.
    """

    def decorate(
        state_machine_class: type[hypothesis.stateful.RuleBasedStateMachine],
    ) -> Callable[[], None]:
        if use_django_executor:
            executor = DjangoHypothesisExecutor()

            class DjangoRuleBasedStateMachine(state_machine_class):  # type: ignore
                @staticmethod
                def setup_example(*args: Any, **kwargs: Any) -> None:
                    executor.setup_example(*args, **kwargs)

                @staticmethod
                def teardown_example(*args: Any, **kwargs: Any) -> None:
                    executor.teardown_example(*args, **kwargs)

            state_machine_class = DjangoRuleBasedStateMachine

        @pytest.mark.usefixtures("django_db_setup", "django_db_blocker")
        def run_as_test() -> None:
            hypothesis.stateful.run_state_machine_as_test(  # type: ignore
                state_machine_class,
                settings=hypothesis.settings(
                    deadline=None,
                    suppress_health_check=hypothesis.HealthCheck.all(),
                ),
            )

        return run_as_test

    return decorate
