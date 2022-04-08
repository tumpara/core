from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import strawberry.types.info

from .views import ApiContext

if TYPE_CHECKING:
    from tumpara.accounts import models as accounts_models

InfoType = strawberry.types.info.Info[ApiContext, None]


def check_authentication(info: InfoType) -> Optional[accounts_models.User]:
    from tumpara.accounts import models as accounts_models

    user = info.context.user
    if user.is_authenticated and user.is_active:
        assert isinstance(user, accounts_models.User)
        return user
    else:
        return None
