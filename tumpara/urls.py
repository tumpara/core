from django import urls

import tumpara.api
import tumpara.photos.views
from tumpara.api.views import ApiView

urlpatterns = [
    urls.path(
        "api/graphql",
        # Note: once we enable subscriptions here, the graphiql.html template needs
        # to be updated from here:
        # https://github.com/strawberry-graphql/strawberry/blob/68901da94c67a7bbd4901d0f0e524da5158442aa/strawberry/static/graphiql.html
        # The subscription-specific stuff was removed because the template isn't
        # currently rendered with any context if it is loaded from the app folder.
        ApiView.as_view(schema_manager=tumpara.api.schema),
    ),
    urls.path(
        "api/photo_thumbnail/<description>",
        tumpara.photos.views.thumbnail_from_description,
        name="photos.thumbnail_from_description",
    ),
]
