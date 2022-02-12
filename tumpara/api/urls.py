import django.urls
import strawberry.django.views
import strawberry.tools

from tumpara.accounts import api as accounts_api

Query = strawberry.tools.merge_types("Query", (accounts_api.Query,))
schema = strawberry.Schema(query=Query)

urlpatterns = [
    django.urls.path(
        "api/graphql",
        # Note: once we enable subscriptions here, the graphiql.html template needs
        # to be updated from here:
        # https://github.com/strawberry-graphql/strawberry/blob/68901da94c67a7bbd4901d0f0e524da5158442aa/strawberry/static/graphiql.html
        # The subscription-specific stuff was removed because the template isn't
        # currently rendered with any context if it is loaded from the app folder.
        strawberry.django.views.GraphQLView.as_view(schema=schema),
    )
]
