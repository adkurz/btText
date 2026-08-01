"""Locate and open the user manual bundled with btText."""

import os
from pathlib import Path

import i18n
from platform_support import app_paths


def get_documentation_directory() -> Path:
    """Return the directory containing generated HTML documentation."""
    return app_paths.get_resource_directory() / "docs"


def get_manual_file(language: str | None = None) -> Path:
    """Return the best available manual, falling back to English."""
    normalized = (language or i18n.get_active_language()).replace("_", "-").lower()
    candidates = (normalized, normalized.split("-", 1)[0], i18n.DEFAULT_LANGUAGE)
    for candidate in dict.fromkeys(candidates):
        manual = get_documentation_directory() / f"manual-{candidate}.html"
        if manual.is_file():
            return manual
    raise FileNotFoundError("No English user manual is available.")


def open_manual(language: str | None = None) -> Path:
    """Open the best available manual with the Windows file association."""
    manual = get_manual_file(language)
    os.startfile(manual)  # type: ignore[attr-defined]
    return manual
