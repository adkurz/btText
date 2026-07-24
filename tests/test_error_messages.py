import ast
import gettext
import tempfile
import unittest
from pathlib import Path

import i18n
from app_settings import SettingsError, SettingsStore
from datamodel import CategoryValidationError, EntityNotFoundError
from error_messages import _FORMATTERS, format_user_error
from user_errors import UserFacingError


class MappingTranslations(gettext.NullTranslations):
    def __init__(self, messages):
        super().__init__()
        self.messages = messages

    def gettext(self, message):
        return self.messages.get(message, message)


class ErrorMessagesTestCase(unittest.TestCase):
    def tearDown(self):
        i18n.initialize("en", "missing-locale-directory")

    def test_model_error_is_formatted_from_code_and_parameters(self):
        error = EntityNotFoundError(
            "category_not_found",
            "Category with ID {id} does not exist",
            id=42,
        )

        self.assertEqual(
            format_user_error(error),
            "The category with ID 42 no longer exists.",
        )

    def test_model_error_is_translated_only_at_ui_boundary(self):
        source = "A category with this name already exists at this level."
        i18n._translation = MappingTranslations(
            {source: "Eine Kategorie mit diesem Namen ist hier bereits vorhanden."}
        )
        error = CategoryValidationError(
            "category_name_duplicate",
            "A category with this name already exists at this level",
        )

        self.assertEqual(
            str(error),
            "A category with this name already exists at this level",
        )
        self.assertEqual(
            format_user_error(error),
            "Eine Kategorie mit diesem Namen ist hier bereits vorhanden.",
        )

    def test_settings_error_localizes_a_structured_nested_reason(self):
        outer_source = "The settings file could not be read: {reason}"
        reason_source = "The shortcut requires at least one modifier."
        i18n._translation = MappingTranslations(
            {
                outer_source: "Die Einstellungsdatei konnte nicht gelesen werden: {reason}",
                reason_source: "Das Tastenkürzel benötigt eine Modifikatortaste.",
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            settings_file.write_text(
                "[hotkeys]\ntoggle_window = T\n",
                encoding="utf-8",
            )

            with self.assertRaises(SettingsError) as context:
                SettingsStore(settings_file).load()

        self.assertEqual(context.exception.code, "settings_read_failed")
        self.assertEqual(
            format_user_error(context.exception),
            "Die Einstellungsdatei konnte nicht gelesen werden: "
            "Das Tastenkürzel benötigt eine Modifikatortaste.",
        )

    def test_unknown_structured_error_uses_safe_fallback(self):
        error = UserFacingError(
            "future_error",
            "Internal diagnostic that must not be shown",
        )

        self.assertEqual(
            format_user_error(error),
            "An unexpected application error occurred.",
        )

    def test_every_declared_application_error_has_a_ui_formatter(self):
        error_constructors = {
            "CategoryValidationError",
            "DataModelError",
            "EntityNotFoundError",
            "HotkeyError",
            "LanguageError",
            "SettingsError",
            "SnippetValidationError",
        }
        declared_codes = set()
        project_root = Path(__file__).resolve().parents[1]
        for relative_file in ("app_settings.py", "datamodel.py", "i18n.py"):
            tree = ast.parse(
                (project_root / relative_file).read_text(encoding="utf-8")
            )
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in error_constructors
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    continue
                declared_codes.add(node.args[0].value)

        self.assertLessEqual(declared_codes, set(_FORMATTERS))


if __name__ == "__main__":
    unittest.main()
