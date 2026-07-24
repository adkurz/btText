"""Localize structured application errors for presentation in the UI."""

from collections.abc import Callable
from typing import Any

from i18n import _
from user_errors import UserFacingError


ErrorFormatter = Callable[[dict[str, Any]], str]


def _format_reason(reason: object) -> str:
    """Localize a nested structured reason or preserve a system diagnostic."""
    if isinstance(reason, BaseException):
        return format_user_error(reason)
    return str(reason)


def _format_database_open_failed(parameters: dict[str, Any]) -> str:
    # Translators: Startup error when the snippet database cannot be opened.
    # {reason} is a technical SQLite or operating-system message.
    return _("The database could not be opened: {reason}").format(
        reason=_format_reason(parameters["reason"])
    )


def _format_database_schema_incomplete(parameters: dict[str, Any]) -> str:
    # Translators: Startup error for a damaged or incomplete snippet database.
    # {missing_tables} is a comma-separated list of technical table names.
    return _(
        "The database schema is incomplete. Missing table(s): "
        "{missing_tables}."
    ).format(**parameters)


def _format_database_version_too_new(parameters: dict[str, Any]) -> str:
    # Translators: Startup error when the database comes from a newer btText and
    # cannot be safely read. Both placeholders are integer schema versions.
    return _(
        "The database was created by a newer version of btText and cannot be "
        "opened. Database schema version: {database_version}; supported "
        "version: {supported_version}."
    ).format(**parameters)


def _format_database_migration_unavailable(parameters: dict[str, Any]) -> str:
    # Translators: Startup error when btText cannot upgrade an older database.
    # {database_version} is its integer schema version.
    return _(
        "No database migration is available from schema version "
        "{database_version}."
    ).format(**parameters)


def _format_database_migration_failed(parameters: dict[str, Any]) -> str:
    # Translators: Startup error when a database upgrade did not reach its target
    # version. The migration name is technical; both versions are integers.
    return _(
        "Database migration {migration_name} did not advance the schema from "
        "version {old_version} to version {new_version}."
    ).format(**parameters)


def _format_category_not_found(parameters: dict[str, Any]) -> str:
    # Translators: Error after a category disappeared before an operation could
    # finish. {id} is its internal integer database ID.
    return _("The category with ID {id} no longer exists.").format(**parameters)


def _format_snippet_not_found(parameters: dict[str, Any]) -> str:
    # Translators: Error after a snippet disappeared before an operation could
    # finish. {id} is its internal integer database ID.
    return _("The snippet with ID {id} no longer exists.").format(**parameters)


def _format_settings_read_failed(parameters: dict[str, Any]) -> str:
    # Translators: Startup error when btText cannot load its settings file.
    # {reason} is a localized validation or operating-system error.
    return _("The settings file could not be read: {reason}").format(
        reason=_format_reason(parameters["reason"])
    )


def _format_settings_save_failed(parameters: dict[str, Any]) -> str:
    # Translators: Error when btText cannot persist changed settings.
    # {reason} is a localized validation or operating-system error.
    return _("The settings file could not be saved: {reason}").format(
        reason=_format_reason(parameters["reason"])
    )


_FORMATTERS: dict[str, ErrorFormatter] = {
    "database_open_failed": _format_database_open_failed,
    # Translators: Fatal startup error when SQLite cannot enforce relationships
    # between categories and snippets.
    "database_foreign_keys_unavailable": lambda parameters: _(
        "SQLite foreign-key support could not be enabled."
    ),
    "database_schema_incomplete": _format_database_schema_incomplete,
    "database_version_too_new": _format_database_version_too_new,
    "database_migration_unavailable": _format_database_migration_unavailable,
    "database_migration_failed": _format_database_migration_failed,
    # Translators: Fatal startup error describing category records without names.
    "database_category_name_missing": lambda parameters: _(
        "The database contains categories without a name."
    ),
    # Translators: Fatal startup error for snippet records whose numeric
    # search-ranking weight is outside the supported range.
    "database_snippet_weight_invalid": lambda parameters: _(
        "The database contains snippets with an invalid weight."
    ),
    # Translators: Fatal startup error for duplicate snippet names in one category.
    "database_snippet_names_duplicate": lambda parameters: _(
        "The database contains duplicate snippet names in a category."
    ),
    # Translators: Fatal startup error for snippets without an existing category.
    "database_snippet_category_missing": lambda parameters: _(
        "The database contains snippets without a category."
    ),
    "category_not_found": _format_category_not_found,
    "snippet_not_found": _format_snippet_not_found,
    # Translators: Validation error when a sibling category already uses this name.
    "category_name_duplicate": lambda parameters: _(
        "A category with this name already exists at this level."
    ),
    # Translators: Internal error for an unsaved category without a database ID.
    "category_id_missing": lambda parameters: _(
        "The category has no ID."
    ),
    # Translators: Error when the intended parent category was deleted meanwhile.
    "category_parent_missing": lambda parameters: _(
        "The parent category no longer exists."
    ),
    # Translators: Validation error preventing a category being its own parent.
    "category_own_parent": lambda parameters: _(
        "A category cannot be its own parent."
    ),
    # Translators: Validation error preventing a move into the category's subtree.
    "category_move_into_descendant": lambda parameters: _(
        "A category cannot be moved below one of its descendants."
    ),
    # Translators: Validation error preventing recursive copying into the same
    # category subtree.
    "category_copy_into_descendant": lambda parameters: _(
        "A category cannot be copied into itself or one of its descendants."
    ),
    # Translators: Validation error for an empty category or snippet name.
    "entity_name_empty": lambda parameters: _(
        "The name must not be empty."
    ),
    # Translators: Validation error when a snippet has no insertion text.
    "snippet_content_empty": lambda parameters: _(
        "The content must not be empty."
    ),
    # Translators: Error when the snippet's selected category was deleted meanwhile.
    "snippet_category_missing": lambda parameters: _(
        "The selected category no longer exists."
    ),
    # Translators: Validation error when a snippet name is already used in the
    # same category.
    "snippet_name_duplicate": lambda parameters: _(
        "A snippet with this name already exists in this category."
    ),
    # Translators: Validation error for a snippet search-ranking weight outside
    # the allowed choices.
    "snippet_weight_invalid": lambda parameters: _(
        "The selected weight is not allowed."
    ),
    # Translators: Internal error for an unsaved snippet without a database ID.
    "snippet_id_missing": lambda parameters: _(
        "The snippet has no ID."
    ),
    # Translators: Validation error when a global shortcut contains an
    # unsupported keyboard key.
    "hotkey_key_unsupported": lambda parameters: _(
        "The shortcut contains an unsupported key."
    ),
    # Translators: Validation error when a global shortcut has no Ctrl, Shift,
    # Alt, or Windows modifier.
    "hotkey_modifier_required": lambda parameters: _(
        "The shortcut requires at least one modifier."
    ),
    # Translators: Validation error when a shortcut from settings cannot be parsed.
    "hotkey_format_invalid": lambda parameters: _(
        "The shortcut has an invalid format."
    ),
    # Translators: Validation error when a shortcut repeats the same modifier.
    "hotkey_modifier_duplicate": lambda parameters: _(
        "The shortcut contains a duplicate modifier."
    ),
    # Translators: Validation error when a shortcut has zero or multiple main keys.
    "hotkey_key_count_invalid": lambda parameters: _(
        "The shortcut must contain exactly one key."
    ),
    # Translators: Validation error when a key cannot be used for a global shortcut.
    "hotkey_key_unusable": lambda parameters: _(
        "This key cannot be used as a shortcut."
    ),
    # Translators: Settings error when the selected UI language has no installed
    # gettext catalog.
    "language_catalog_unavailable": lambda parameters: _(
        "No translation catalog is available for the selected language."
    ),
    # Translators: Settings error when the saved UI language code is malformed.
    "language_format_invalid": lambda parameters: _(
        "The language setting has an invalid format."
    ),
    "settings_read_failed": _format_settings_read_failed,
    "settings_save_failed": _format_settings_save_failed,
}


def format_user_error(error: BaseException) -> str:
    """Return a localized user-facing representation of ``error``."""
    if not isinstance(error, UserFacingError):
        return str(error)
    formatter = _FORMATTERS.get(error.code)
    if formatter is None:
        # Translators: Safe fallback when no specific localized application-error
        # message is available.
        return _("An unexpected application error occurred.")
    return formatter(error.parameters)
