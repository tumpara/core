import os
from pathlib import Path

os.environ.setdefault("TUMPARA_SECRET_KEY", "thisisnotsecure")
os.environ.setdefault("TUMPARA_ENABLE_DEMO_BACKEND", "True")
os.environ.setdefault(
    "TUMPARA_EXIFTOOL_BINARY",
    str(Path(__file__).parent.parent.parent / ".dev" / "bin" / "exiftool"),
)

# pylint: disable-next=wildcard-import, unused-wildcard-import, wrong-import-position
from .base import *

DEBUG = True

# An empty allowed hosts config will allow connections to localhost when DEBUG is
# active. See: https://docs.djangoproject.com/en/3.1/ref/settings/#allowed-hosts
ALLOWED_HOSTS = []

# Disable password validators in development mode.
AUTH_PASSWORD_VALIDATORS = []

# Effectively disable all crossorigin headers.
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
