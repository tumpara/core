import functools

from hypothesis import strategies as st

optional_booleans = functools.partial(st.sampled_from, [None, True, False])

# GraphQL Ints may only be signed 32 bit.
graphql_ints = functools.partial(
    st.integers, min_value=-(2 ** 31) + 1, max_value=2 ** 31 - 1
)

# Values for the 'field_name' parameter of filters and filter sets.
field_names = functools.partial(st.from_regex, r"^[a-z0-9]+(__?[a-z0-9]+)")


@st.composite
def usernames(draw: st.DrawFn) -> str:
    """Generate valid Django usernames."""
    from django.contrib.auth.base_user import AbstractBaseUser

    username = draw(st.from_regex(r"[\w.@+-]+", fullmatch=True))
    return AbstractBaseUser.normalize_username(username)
