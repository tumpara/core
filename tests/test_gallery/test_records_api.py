import pytest

from tumpara.accounts.models import User
from tumpara.gallery.models import Note
from tumpara.libraries.models import Library

from .test_notes_api import user  # noqa: F401


@pytest.fixture
def library(user: User) -> Library:
    library = Library.objects.create(source="testing:///", context="test_storage")
    library.add_membership(user, owner=True)
    return library


@pytest.fixture
def notes(library: Library) -> set[Note]:
    return {
        Note.objects.create(library=library, content="First note."),
        Note.objects.create(library=library, content="Second note."),
        Note.objects.create(library=library, content="Third note."),
        Note.objects.create(library=library, content="Fourth note."),
        Note.objects.create(library=library, content="Fifth note."),
        Note.objects.create(library=library, content="Sixth note."),
        Note.objects.create(library=library, content="Seventh note."),
        Note.objects.create(library=library, content="Eighth note."),
        Note.objects.create(library=library, content="Ninth note."),
        Note.objects.create(library=library, content="Tenth note."),
    }


@pytest.mark.django_db
def test_listing_records(notes: set[Note]) -> None:
    pass
