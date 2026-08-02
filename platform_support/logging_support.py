"""Open the writable directory containing btText application logs."""

import os
from pathlib import Path

from platform_support import app_paths


def open_log_directory() -> Path:
    """Create and open the active log directory in Windows Explorer."""
    directory = app_paths.get_log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    os.startfile(directory)  # type: ignore[attr-defined]
    return directory
