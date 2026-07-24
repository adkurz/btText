"""Initialize and expose process-wide user-interface translations."""

import gettext
import locale
import re
import struct
from pathlib import Path
from typing import Any

from user_errors import UserFacingError


DOMAIN = "bttext"
DEFAULT_LANGUAGE = "en"
SYSTEM_LANGUAGE = "system"

_translation: gettext.NullTranslations = gettext.NullTranslations()
_wx_locale: Any | None = None
_active_language = DEFAULT_LANGUAGE


class LanguageError(UserFacingError, ValueError):
    """Raised when a language code or catalog selection is invalid."""


def get_available_languages(locale_directory: str | Path) -> tuple[str, ...]:
    """Return source English and every language with a compiled catalog."""
    languages = {DEFAULT_LANGUAGE}
    locale_path = Path(locale_directory)
    if locale_path.is_dir():
        try:
            language_directories = tuple(locale_path.iterdir())
        except OSError:
            language_directories = ()
        for language_directory in language_directories:
            catalog = (
                language_directory
                / "LC_MESSAGES"
                / "{}.mo".format(DOMAIN)
            )
            if not catalog.is_file():
                continue
            try:
                normalized_language = _normalize_language_code(
                    language_directory.name
                )
            except ValueError:
                continue
            if normalized_language == language_directory.name:
                languages.add(normalized_language)
    return tuple(
        sorted(
            languages,
            key=lambda language: (language != DEFAULT_LANGUAGE, language),
        )
    )


def get_language_display_name(
    language: str,
    wx_module: Any | None = None,
) -> str:
    """Return a native language name, falling back to its stable code."""
    if language == SYSTEM_LANGUAGE:
        # Translators: Language-choice entry that follows the operating
        # system's language when a matching catalog is installed.
        return _("System default")
    if wx_module is None:
        return language
    try:
        language_info = wx_module.Locale.FindLanguageInfo(language)
    except (AttributeError, TypeError, ValueError):
        return language
    if language_info is None:
        return language
    return (
        getattr(language_info, "DescriptionNative", None)
        or getattr(language_info, "Description", None)
        or language
    )


def validate_language(
    language: str,
    locale_directory: str | Path | None = None,
) -> str:
    """Normalize a setting and optionally require an available catalog."""
    if language.strip().lower() == SYSTEM_LANGUAGE:
        return SYSTEM_LANGUAGE
    normalized_language = _normalize_language_code(language)
    if locale_directory is None:
        return normalized_language
    available_languages = get_available_languages(locale_directory)
    matched_language = _match_available_language(
        normalized_language,
        available_languages,
    )
    if matched_language is None:
        raise LanguageError(
            "language_catalog_unavailable",
            "No translation catalog is available for the language",
        )
    return matched_language


def resolve_language(
    language: str,
    locale_directory: str | Path,
    wx_module: Any | None = None,
) -> str:
    """Resolve a setting to source English or an available catalog language."""
    normalized_language = validate_language(language)
    available_languages = get_available_languages(locale_directory)
    if normalized_language != SYSTEM_LANGUAGE:
        matched_language = _match_available_language(
            normalized_language,
            available_languages,
        )
        if matched_language is None:
            raise LanguageError(
                "language_catalog_unavailable",
                "No translation catalog is available for the language",
            )
        return matched_language

    system_locale = _get_system_language(wx_module)
    if system_locale:
        try:
            system_language = _normalize_language_code(system_locale)
        except ValueError:
            pass
        else:
            matched_language = _match_available_language(
                system_language,
                available_languages,
            )
            if matched_language is not None:
                return matched_language
    return DEFAULT_LANGUAGE


def initialize(
    language: str,
    locale_directory: str | Path,
    wx_module: Any | None = None,
) -> str:
    """Load translations and return the resolved active language."""
    global _active_language, _translation, _wx_locale

    locale_path = Path(locale_directory)
    active_language = resolve_language(language, locale_path, wx_module)
    catalog_error = None
    catalog_exception = None
    try:
        translation = gettext.translation(
            DOMAIN,
            localedir=locale_path,
            languages=[active_language],
            fallback=True,
        )
    except (EOFError, OSError, struct.error, UnicodeError) as error:
        translation = gettext.NullTranslations()
        catalog_exception = error
        catalog_error = LanguageError(
            "language_catalog_load_failed",
            "The translation catalog for {language} could not be loaded: "
            "{reason}",
            language=active_language,
            reason=error,
        )
        active_language = DEFAULT_LANGUAGE

    wx_locale = _create_wx_locale(active_language, locale_path, wx_module)
    _translation, _active_language, _wx_locale = (
        translation,
        active_language,
        wx_locale,
    )
    if catalog_error is not None:
        raise catalog_error from catalog_exception
    return active_language


def get_active_language() -> str:
    """Return the resolved language currently used for translations."""
    return _active_language


def gettext_(message: str) -> str:
    """Translate a singular message in the application domain."""
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
    """Translate a message using the plural form appropriate for ``count``."""
    return _translation.ngettext(singular, plural, count)


def pgettext(context: str, message: str) -> str:
    """Translate a message disambiguated by ``context``."""
    return _translation.pgettext(context, message)


_ = gettext_


def _normalize_language_code(language: str) -> str:
    """Normalize a safe gettext language code without accessing the filesystem."""
    parts = re.split(r"[-_]", language.strip())
    if not (
        2 <= len(parts[0]) <= 3
        and parts[0].isascii()
        and parts[0].isalpha()
        and all(
            2 <= len(part) <= 8
            and part.isascii()
            and part.isalnum()
            for part in parts[1:]
        )
    ):
        raise LanguageError(
            "language_format_invalid",
            "The language setting has an invalid format",
        )

    normalized_parts = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 2 and part.isalpha():
            normalized_parts.append(part.upper())
        elif len(part) == 4 and part.isalpha():
            normalized_parts.append(part.title())
        else:
            normalized_parts.append(part.lower())
    return "_".join(normalized_parts)


def _match_available_language(
    language: str,
    available_languages: tuple[str, ...],
) -> str | None:
    """Match an exact language or its base language against available catalogs."""
    if language in available_languages:
        return language
    base_language = language.split("_", 1)[0]
    if base_language in available_languages:
        return base_language
    return None


def _get_system_language(wx_module: Any | None) -> str | None:
    """Return a locale code, preferring wx after it resets Python's locale."""
    if wx_module is not None:
        try:
            language = wx_module.Locale.GetSystemLanguage()
            language_info = wx_module.Locale.GetLanguageInfo(language)
        except (AttributeError, TypeError, ValueError):
            language_info = None
        if language_info is not None:
            canonical_name = getattr(language_info, "CanonicalName", None)
            if canonical_name:
                return canonical_name

    try:
        return locale.getlocale()[0]
    except (ValueError, locale.Error):
        return None


def _create_wx_locale(
    language: str,
    locale_directory: Path,
    wx_module: Any | None,
) -> Any | None:
    """Initialize wxWidgets locale support when wxPython is available."""
    if wx_module is None:
        return None

    try:
        language_info = wx_module.Locale.FindLanguageInfo(language)
        if language_info is None:
            return None
        wx_module.Locale.AddCatalogLookupPathPrefix(str(locale_directory))
        wx_locale = wx_module.Locale(language_info.Language)
        if not wx_locale.AddCatalog(DOMAIN):
            return None
    except Exception:
        return None
    return wx_locale
