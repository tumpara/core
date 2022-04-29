from collections.abc import Sequence

import pytest

from tumpara.testing.conftest import *  # noqa: F401


@pytest.fixture
def patch_exception_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """This fixture will patch various storage-related APIs that handle exceptions by
    logging and then ignoring them to raise them instead. That way we can make sure that
    our stuff doesn't actually raise exceptions."""
    from tumpara.libraries import signals as libraries_signals
    from tumpara.libraries.scanner import runner

    monkeypatch.setattr(runner, "RAISE_EXCEPTIONS", True)

    # Use send() on the signals instead of send_robust() because that way our tests fail
    # if errors occur (which we don't want, but in production we just ignore them).
    monkeypatch.setattr(
        libraries_signals.new_file,
        "send_robust",
        libraries_signals.new_file.send,
    )
    monkeypatch.setattr(
        libraries_signals.files_changed,
        "send_robust",
        libraries_signals.files_changed.send,
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run expensive and / or slow tests.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: mark test as slow to run")


def pytest_collection_modifyitems(
    config: pytest.Config, items: Sequence[pytest.Item]
) -> None:
    if not config.getoption("--run-slow"):
        skip_marker = pytest.mark.skip(
            reason="Won't run expensive test unless --run-slow is given."
        )
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_marker)
