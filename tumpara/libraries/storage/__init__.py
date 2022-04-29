from .base import LibraryStorage, StorageValidationError, WatchGenerator, backends

__all__ = [
    "LibraryStorage",
    "StorageValidationError",
    "WatchGenerator",
    "backends",
    "register",
]

# Provide a shortcut for registering custom backends. This is also mentioned in the
# documentation for backends.register().
register = backends.register
