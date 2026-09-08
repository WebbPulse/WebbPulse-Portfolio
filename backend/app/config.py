"""The application's settings, re-exported from the composition package.

The class itself moved to `app/composition/settings.py` in PR 4, because
settings are now something the two composition roots share rather than
something the monolith owns. This module stays as the import path the rest of
the application already uses, so a domain module keeps saying
`from ...config import settings` and does not need to know which root built it.

The one behaviour change is documented in `app.composition.settings`: the four
secret fields no longer raise at construction, so importing anything under
`app/` now works with no AWS credentials and no environment at all.
"""

from .composition.settings import (
    DEFAULT_CORS_ORIGINS,
    LOCALHOST_ORIGINS,
    SECRET_FIELDS,
    Settings,
    get_settings,
    reset_settings_cache,
    settings,
)

__all__ = [
    "DEFAULT_CORS_ORIGINS",
    "LOCALHOST_ORIGINS",
    "SECRET_FIELDS",
    "Settings",
    "get_settings",
    "reset_settings_cache",
    "settings",
]
