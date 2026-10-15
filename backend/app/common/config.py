"""The application's settings, re-exported from the composition package.

The import path the rest of the application uses, so a domain module need not
know which composition root built the settings it reads.
"""

from .composition.settings import (
    DEFAULT_CORS_ORIGINS,
    LOCALHOST_ORIGINS,
    Settings,
    get_settings,
    reset_settings_cache,
    settings,
)

__all__ = [
    "DEFAULT_CORS_ORIGINS",
    "LOCALHOST_ORIGINS",
    "Settings",
    "get_settings",
    "reset_settings_cache",
    "settings",
]
