import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.app_settings import (
    APPEARANCE_DARK,
    APPEARANCE_SYSTEM,
    AppSettings,
    SettingsError,
    SettingsStore,
)
from core.shortcuts import Hotkey


class SettingsStoreTestCase(unittest.TestCase):
    @staticmethod
    def _add_catalog(locale_directory, language):
        catalog = (
            Path(locale_directory)
            / language
            / "LC_MESSAGES"
            / "bttext.mo"
        )
        catalog.parent.mkdir(parents=True)
        catalog.touch()

    def test_missing_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = SettingsStore(Path(temporary_directory) / "settings.ini")

            self.assertEqual(store.load(), AppSettings())

    def test_settings_are_saved_and_loaded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            store = SettingsStore(settings_file)
            settings = AppSettings(
                database_file=str(
                    Path(temporary_directory) / "snippets.db"
                ),
                toggle_window_hotkey=Hotkey.parse("CTRL+ALT+F8"),
                language="de",
                appearance=APPEARANCE_DARK,
                include_copied_text_in_clipboard_history=False,
                allow_copied_text_cloud_upload=False,
                hotstrings_enabled=False,
                preserve_hotstring_boundary=False,
                notify_hotstring_expansion=True,
            )

            store.save(settings)

            self.assertEqual(store.load(), settings)
            self.assertIn(
                "database_file = ",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "toggle_window = CTRL+ALT+F8",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "language = de",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "[design]",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "appearance = dark",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "include_copied_text_in_clipboard_history = False",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "allow_copied_text_cloud_upload = False",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "[hotstrings]",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "enabled = False",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "preserve_boundary = False",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "notify_expansion = True",
                settings_file.read_text(encoding="utf-8"),
            )

    def test_language_defaults_to_system(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            settings_file.write_text(
                "[hotkeys]\ntoggle_window = CTRL+ALT+F8\n",
                encoding="utf-8",
            )

            settings = SettingsStore(settings_file).load()

            self.assertEqual(settings.language, "system")
            self.assertEqual(settings.appearance, APPEARANCE_SYSTEM)
            self.assertTrue(settings.include_copied_text_in_clipboard_history)
            self.assertTrue(settings.allow_copied_text_cloud_upload)
            self.assertTrue(settings.hotstrings_enabled)
            self.assertTrue(settings.preserve_hotstring_boundary)
            self.assertFalse(settings.notify_hotstring_expansion)
            self.assertIsNone(settings.database_file)

    def test_invalid_appearance_falls_back_to_system(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            settings_file.write_text(
                "[design]\nappearance = sepia\n",
                encoding="utf-8",
            )

            settings = SettingsStore(settings_file).load()

            self.assertEqual(settings.appearance, APPEARANCE_SYSTEM)

    def test_general_appearance_is_not_migrated(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            settings_file.write_text(
                "[general]\nappearance = dark\n",
                encoding="utf-8",
            )

            settings = SettingsStore(settings_file).load()

            self.assertEqual(settings.appearance, APPEARANCE_SYSTEM)

    def test_database_beside_settings_file_is_saved_portably(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            settings_file = directory / "settings.ini"
            database_file = directory / "data.db"
            store = SettingsStore(settings_file)

            store.save(AppSettings(database_file=str(database_file)))

            contents = settings_file.read_text(encoding="utf-8")
            self.assertIn("database_file = data.db", contents)
            self.assertNotIn(str(directory.resolve()), contents)
            self.assertEqual(
                store.load().database_file,
                str(database_file.resolve()),
            )

    def test_external_database_is_saved_as_absolute_path(self):
        with (
            tempfile.TemporaryDirectory() as settings_directory,
            tempfile.TemporaryDirectory() as database_directory,
        ):
            settings_file = Path(settings_directory) / "settings.ini"
            database_file = Path(database_directory) / "snippets.db"
            store = SettingsStore(settings_file)

            store.save(AppSettings(database_file=str(database_file)))

            self.assertIn(
                "database_file = {}".format(database_file.resolve()),
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                store.load().database_file,
                str(database_file.resolve()),
            )

    def test_obsolete_general_hotstring_keys_are_not_migrated(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            settings_file.write_text(
                "[general]\n"
                "hotstrings_enabled = false\n"
                "preserve_hotstring_boundary = false\n"
                "notify_hotstring_expansion = true\n",
                encoding="utf-8",
            )

            settings = SettingsStore(settings_file).load()

            self.assertTrue(settings.hotstrings_enabled)
            self.assertTrue(settings.preserve_hotstring_boundary)
            self.assertFalse(settings.notify_hotstring_expansion)

    def test_language_is_normalized(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            locale_directory = Path(temporary_directory) / "locale"
            self._add_catalog(locale_directory, "de")
            settings_file.write_text(
                "[general]\nlanguage = de-DE\n",
                encoding="utf-8",
            )

            settings = SettingsStore(
                settings_file,
                locale_directory,
            ).load()

            self.assertEqual(settings.language, "de")

    def test_language_without_catalog_raises_settings_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            settings_file.write_text(
                "[general]\nlanguage = fr\n",
                encoding="utf-8",
            )

            with self.assertRaises(SettingsError):
                SettingsStore(
                    settings_file,
                    Path(temporary_directory) / "locale",
                ).load()

    def test_language_without_catalog_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"

            with self.assertRaises(SettingsError):
                SettingsStore(
                    settings_file,
                    Path(temporary_directory) / "locale",
                ).save(AppSettings(language="fr"))

            self.assertFalse(settings_file.exists())

    def test_invalid_file_raises_settings_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            settings_file.write_text(
                "[hotkeys]\ntoggle_window = T\n",
                encoding="utf-8",
            )
            store = SettingsStore(settings_file)

            with self.assertRaises(SettingsError) as context:
                store.load()

            self.assertEqual(context.exception.code, "settings_read_failed")

    def test_open_error_is_reported_as_settings_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = SettingsStore(Path(temporary_directory) / "settings.ini")

            with patch.object(Path, "open", side_effect=OSError("access denied")):
                with self.assertRaisesRegex(SettingsError, "access denied"):
                    store.save(AppSettings())

    def test_replace_error_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            temporary_file = Path(temporary_directory) / "settings.ini.tmp"
            store = SettingsStore(settings_file)

            with patch.object(
                Path,
                "replace",
                side_effect=OSError("replace failed"),
            ):
                with self.assertRaisesRegex(SettingsError, "replace failed"):
                    store.save(AppSettings())

            self.assertFalse(temporary_file.exists())


if __name__ == "__main__":
    unittest.main()
