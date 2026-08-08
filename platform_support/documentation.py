"""Locate and open localized documentation bundled with btText."""

from pathlib import Path

from platform_support import app_paths
from platform_support.shell import open_path


DEFAULT_DOCUMENTATION_LANGUAGE = "en"


def get_documentation_directory() -> Path:
    """Return the directory containing generated HTML documentation."""
    return app_paths.get_resource_directory() / "docs"


def _language_candidates(language: str) -> tuple[str, ...]:
    """Return normalized exact, base, and English fallback languages."""
    normalized = language.replace("_", "-").lower()
    candidates = (
        normalized,
        normalized.split("-", 1)[0],
        DEFAULT_DOCUMENTATION_LANGUAGE,
    )
    return tuple(dict.fromkeys(candidates))


def get_manual_file(language: str) -> Path:
    """Return the best available manual, falling back to English."""
    for candidate in _language_candidates(language):
        manual = get_documentation_directory() / f"manual-{candidate}.html"
        if manual.is_file():
            return manual
    raise FileNotFoundError("No English user manual is available.")


def get_changelog_file(language: str) -> Path:
    """Return the best available changelog, falling back to English."""
    for candidate in _language_candidates(language):
        changelog = get_documentation_directory() / f"changelog-{candidate}.html"
        if changelog.is_file():
            return changelog
    raise FileNotFoundError("No English changelog is available.")


def open_manual(language: str) -> Path:
    """Open the best available manual with the Windows file association."""
    manual = get_manual_file(language)
    open_path(manual)
    return manual


def open_changelog(language: str) -> Path:
    """Open the best available changelog with the Windows file association."""
    changelog = get_changelog_file(language)
    open_path(changelog)
    return changelog
