import datetime
from typing import Any

import django.test
import freezegun
import hypothesis
import pytest
from django.utils import timezone

from tumpara import api
from tumpara.accounts.models import User
from tumpara.api.models import Token
from tumpara.testing import strategies as st

from ..test_accounts.utils import user_dataset  # noqa: F401
from ..test_accounts.utils import UserDataset

create_token_mutation = """
    mutation CreateToken($username: String!, $password: String!) {
        createToken(credentials: [$username, $password], name: "Test token") {
            __typename
            ...on Token {
                key
                header
            }
            ...on InvalidCredentialsError {
              scope
            }
        }
    }
"""


@pytest.mark.django_db
def test_username_password_token(user_dataset: UserDataset) -> None:
    """Tokens can be created by supplying the correct username and password."""
    user = user_dataset[0]
    password = "nots@fe!"
    user.set_password(password)
    user.save()

    result = api.execute_sync(
        create_token_mutation, username=user.username, password="wrong"
    )
    assert result.errors is None
    assert result.data is not None
    assert result.data["createToken"] == {
        "__typename": "InvalidCredentialsError",
        "scope": user.username,
    }
    assert not Token.objects.exists()

    result = api.execute_sync(
        create_token_mutation, username=user.username, password=password
    )
    assert result.errors is None
    assert result.data is not None
    assert result.data["createToken"]["__typename"] == "Token"
    assert Token.objects.count() == 1
    assert (
        Token.objects.filter_valid()
        .filter(key=result.data["createToken"]["key"], name="Test token")
        .exists()
    )


@hypothesis.given(
    st.usernames(), st.text(min_size=4), st.usernames(), st.text(min_size=4)
)
def test_wrong_credentials_token(
    django_executor: Any,
    username: str,
    password: str,
    wrong_username: str,
    wrong_password: str,
) -> None:
    """Wrong usernames and / or passwords don't yield a token."""
    hypothesis.assume(username != wrong_username)
    hypothesis.assume(password != wrong_password)
    user = User.objects.create_user(username, "", password)

    first_result = api.execute_sync(
        create_token_mutation, username=username, password=wrong_password
    )
    second_result = api.execute_sync(
        create_token_mutation, username=wrong_username, password=password
    )
    third_result = api.execute_sync(
        create_token_mutation, username=wrong_username, password=wrong_password
    )

    for result in (first_result, second_result, third_result):
        assert result.errors is None
        assert result.data is not None
        assert result.data["createToken"]["__typename"] == "InvalidCredentialsError"
        assert not Token.objects.exists()


@hypothesis.given(
    st.from_regex(r"#[.\\-_a-zA-Z0-9]+", fullmatch=True),
    st.lists(st.text(), min_size=0, max_size=4),
)
def test_invalid_method_token(
    django_executor: Any, method: str, extra_credentials: list[str]
) -> None:
    """Invalid authentication methods don't yield a token."""
    result = api.execute_sync(
        """mutation TryAuthentication($credentials: [String!]!) {
            createToken(credentials: $credentials, name: "Test token") {
                __typename
                ...on UnknownAuthenticationMethodError {
                  method
                }
            }
        }""",
        credentials=[method, *extra_credentials],
    )
    assert result.errors is None
    assert result.data is not None
    assert result.data["createToken"] == {
        "__typename": "UnknownAuthenticationMethodError",
        "method": method,
    }
    assert not Token.objects.exists()


me_query = """
    query Me {
        me {
            username
        }
    }
"""


@pytest.mark.django_db
def test_api_context_user_from_token(user_dataset: UserDataset) -> None:
    """The ``me`` query returns the expected result. This basically tests whether
    the provided token is correctly applied."""
    user = user_dataset[0]
    token = user.api_tokens.create(
        expiry_timestamp=timezone.now() + datetime.timedelta(hours=1)
    )

    first_result = api.execute_sync(me_query, user)
    second_result = api.execute_sync(me_query, token)

    for result in (first_result, second_result):
        assert result.errors is None
        assert result.data is not None
        assert result.data["me"] == {"username": user.username}


def test_anonymous_api_context() -> None:
    """Anonymous sessions are not logged in."""
    result = api.execute_sync(me_query)
    assert result.errors is None
    assert result.data is not None
    assert result.data["me"] is None


@pytest.mark.django_db
def test_token_expiry_filtering(user_dataset: UserDataset) -> None:
    """Filtering expired tokens works as expected."""
    user = user_dataset[0]
    token = user.api_tokens.create(
        expiry_timestamp=timezone.now() + datetime.timedelta(minutes=10)
    )

    assert token in Token.objects.filter_valid()
    with freezegun.freeze_time(timezone.now() + datetime.timedelta(minutes=10)):
        assert token not in Token.objects.filter_valid()


@hypothesis.given(st.usernames(), st.usernames())
def test_token_creation_via_http(
    django_executor: Any, client: django.test.Client, username: str, password: str
) -> None:
    """Simulate an entire token authentication flow, via actual HTTP requests."""
    user = User.objects.create_user(username, "", password)

    response = client.post(
        "/api/graphql", {"query": me_query}, content_type="application/json"
    )
    result = response.json()
    assert "errors" not in result
    assert result["data"]["me"] is None

    response = client.post(
        "/api/graphql",
        {
            "query": create_token_mutation,
            "variables": {"username": username, "password": password},
        },
        content_type="application/json",
    )
    result = response.json()
    assert "errors" not in result
    assert result["data"]["createToken"]["__typename"] == "Token"
    token = result["data"]["createToken"]["header"]

    response = client.post(
        "/api/graphql",
        {"query": me_query},
        content_type="application/json",
        HTTP_X_TOKEN=token,
    )
    result = response.json()
    assert "errors" not in result
    assert result["data"]["me"]["username"] == username

    with freezegun.freeze_time(timezone.now() + datetime.timedelta(days=7, seconds=2)):
        response = client.post(
            "/api/graphql",
            {"query": me_query},
            content_type="application/json",
            HTTP_X_TOKEN=token,
        )
        result = response.json()
        assert "errors" not in result
        assert result["data"]["me"] is None
