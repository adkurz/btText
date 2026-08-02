"""Locate and open localized documentation bundled with btText."""

import os
from pathlib import Path

import i18n
from platform_support import app_paths


def get_documentation_directory() -> Path:
    """Return the directory containing generated HTML documentation."""
    return app_paths.get_resource_directory() / "docs"


def _language_candidates(language: str | None = None) -> tuple[str, ...]:
    """Return normalized exact, base, and English fallback languages."""
    normalized = (language or i18n.get_active_language()).replace("_", "-").lower()
    candidates = (normalized, normalized.split("-", 1)[0], i18n.DEFAULT_LANGUAGE)
    return tuple(dict.fromkeys(candidates))


def get_manual_file(language: str | None = None) -> Path:
    """Return the best available manual, falling back to English."""
    for candidate in _language_candidates(language):
        manual = get_documentation_directory() / f"manual-{candidate}.html"
        if manual.is_file():
            return manual
    raise FileNotFoundError("No English user manual is available.")


def get_changelog_file(language: str | None = None) -> Path:
    """Return the best available changelog, falling back to English."""
    for candidate in _language_candidates(language):
        changelog = get_documentation_directory() / f"changelog-{candidate}.html"
        if changelog.is_file():
            return changelog
    raise FileNotFoundError("No English changelog is available.")


def open_manual(language: str | None = None) -> Path:
    """Open the best available manual with the Windows file association."""
    manual = get_manual_file(language)
    os.startfile(manual)  # type: ignore[attr-defined]
    return manual


def open_changelog(language: str | None = None) -> Path:
    """Open the best available changelog with the Windows file association."""
    changelog = get_changelog_file(language)
    os.startfile(changelog)  # type: ignore[attr-defined]
    return changelog
