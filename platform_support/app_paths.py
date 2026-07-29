"""Resolve writable data and bundled-resource paths for all launch modes."""

import os
import sys
from enum import Enum
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALL_MODE_MARKER = "bttext-install-mode.json"
USER_DATA_DIRECTORY_NAME = "btText"


class ApplicationMode(Enum):
    """Describe how the current application instance was launched."""

    SOURCE = "source"
    PORTABLE = "portable"
    INSTALLED = "installed"


def get_application_mode() -> ApplicationMode:
    """Return the explicit source, portable, or installed launch mode."""
    if not getattr(sys, "frozen", False):
        return ApplicationMode.SOURCE
    marker = get_resource_directory() / INSTALL_MODE_MARKER
    if marker.is_file():
        return ApplicationMode.INSTALLED
    return ApplicationMode.PORTABLE


def get_application_directory() -> Path:
    """Return the directory containing the executable or source project."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def get_resource_directory() -> Path:
    """Return the directory containing bundled application resources."""
    bundle_directory = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle_directory is not None:
        return Path(bundle_directory).resolve()
    return PROJECT_ROOT


def get_user_data_directory() -> Path:
    """Return the per-user application data directory used when installed."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError(
            "APPDATA is unavailable; the installed data directory "
            "cannot be resolved."
        )
    return Path(appdata).expanduser().resolve() / USER_DATA_DIRECTORY_NAME


def get_data_directory() -> Path:
    """Return the writable directory for settings and application data."""
    if get_application_mode() is ApplicationMode.INSTALLED:
        directory = get_user_data_directory()
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    return get_application_directory()


def get_database_file() -> Path:
    """Return the default database in the active writable data directory."""
    return get_data_directory() / "data.db"


def get_icon_file() -> Path:
    """Return the bundled application icon path."""
    return get_resource_directory() / "assets" / "icon.png"


def get_locale_directory() -> Path:
    """Return the directory containing bundled translation catalogs."""
    return get_resource_directory() / "locale"


def get_settings_file() -> Path:
    """Return the INI file in the active writable data directory."""
    return get_data_directory() / "settings.ini"
