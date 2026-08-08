"""Open the writable directory containing btText application logs."""

from pathlib import Path

from platform_support import app_paths
from platform_support.shell import open_path


def open_log_directory() -> Path:
    """Create and open the active log directory in Windows Explorer."""
    directory = app_paths.get_log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    open_path(directory)
    return directory
