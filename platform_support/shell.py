"""Open files and directories through Windows shell associations."""

import os
from pathlib import Path


def open_path(path: str | Path) -> Path:
    """Resolve and open ``path`` through its Windows shell association."""
    resolved_path = Path(path).expanduser().resolve()
    os.startfile(resolved_path)  # type: ignore[attr-defined]
    return resolved_path


def open_containing_directory(file_path: str | Path) -> Path:
    """Open and return the resolved directory containing ``file_path``."""
    directory = Path(file_path).expanduser().resolve().parent
    return open_path(directory)
