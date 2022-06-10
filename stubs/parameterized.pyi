from typing import Any, Callable, TypeVar  # noqa: F401

_T = TypeVar("_T", bound="Callable[Any, Any]")

# Since we only use parametrized in tests anyway, we don't really need to bother
# creating strict type stubs.
class parameterized(object):
    def __call__(self, test_func: _T) -> _T: ...
    @classmethod
    def expand(cls, input: _T) -> _T: ...
