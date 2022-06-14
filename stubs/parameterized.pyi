from typing import Any, Callable, TypeVar  # noqa: F401

_T = TypeVar("_T", bound="Callable[..., Any]")

# Since we only use parametrized in tests anyway, we don't really need to bother
# creating strict type stubs.
class parameterized(object):
    def __call__(self, test_func: _T) -> _T: ...
    @staticmethod
    def expand(input: Any) -> Callable[[_T], _T]: ...
