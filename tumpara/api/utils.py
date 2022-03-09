import strawberry.types.info

from .views import ApiContext

InfoType = strawberry.types.info.Info[ApiContext, None]


def check_authentication(info: InfoType) -> bool:
    user = info.context.user
    return user.is_authenticated and user.is_active
