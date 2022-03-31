from tumpara.settings.testing import *

# Additionally install all tests apps define their own models (the other ones are not
# needed).
INSTALLED_APPS += [
    "tests.test_accounts",
    "tests.test_storage",
]


TESTDATA_ROOT = DATA_ROOT / "testdata"
PREVIEW_ROOT = DATA_ROOT / "previews-test"
