from typing import Any, ContextManager, Optional

class SubTests:
    def test(self, msg: Optional[str], **kwargs: Any) -> ContextManager[None]: ...
