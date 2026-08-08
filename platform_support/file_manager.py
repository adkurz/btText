"""Open application-relevant locations in the Windows file manager."""

import os
from pathlib import Path


def open_containing_directory(file_path: str | Path) -> Path:
    """Open and return the directory containing ``file_path``."""
    directory = Path(file_path).expanduser().resolve().parent
    os.startfile(directory)  # type: ignore[attr-defined]
    return directory
