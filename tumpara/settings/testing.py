import tempfile

from .development import *  # pylint: disable=wildcard-import, unused-wildcard-import

# Force an in-memory test database (since we are testing with SQLite). Pytest
# normally automatically does it, but not currently when using xdist with a
# spaciallite database. See here: https://github.com/pytest-dev/pytest-django/issues/88
DATABASES["default"]["NAME"] = ":memory:"

# Downgrade to a faster password hasher during testing to speed up the process.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

THUMBNAIL_PATH = tempfile.mkdtemp()
THUMBNAIL_STORAGE = FileSystemStorage(THUMBNAIL_PATH)
