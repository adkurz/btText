import sys
from pathlib import Path


def get_application_directory() -> Path:
    """Return the directory that contains the portable application."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_resource_directory() -> Path:
    """Return the directory containing bundled application resources."""
    bundle_directory = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle_directory is not None:
        return Path(bundle_directory).resolve()
    return Path(__file__).resolve().parent


def get_database_file() -> Path:
    return get_application_directory() / "data.db"


def get_icon_file() -> Path:
    return get_resource_directory() / "assets" / "icon.png"
