import pytest

from tumpara import api
from tumpara.accounts import models as accounts_models
from tumpara.api import schema

mutation = """
    fragment Result on LibraryMutationResult {
        __typename
        ... on FormError {
            fields
            codes
        }
        ... on NodeError {
            requestedId
        }
        ... on Library {
            id
            source
            context
        }
    }

    mutation CreateLibrary($input: CreateLibraryInput!) {
        createLibrary(input: $input) {
            ...Result
        }
    }

    mutation EditLibrary($input: EditLibraryInput!) {
        editLibrary(input: $input) {
            ...Result
        }
    }
"""


@pytest.mark.django_db
def test_library_creating() -> None:
    result = schema.execute_sync(
        mutation,
        None,
        "CreateLibrary",
        input={"source": "testing:///", "context": "test_storage"},
    )
    assert result.errors is None
    assert result.data == {
        "createLibrary": {
            "__typename": "NodeError",
            "requestedId": None,
        }
    }
