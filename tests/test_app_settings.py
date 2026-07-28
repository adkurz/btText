import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_settings import (
    AppSettings,
    DEFAULT_TOGGLE_HOTKEY,
    Hotkey,
    SettingsError,
    SettingsStore,
)


class HotkeyTestCase(unittest.TestCase):
    def test_hotkey_round_trip(self):
        hotkey = Hotkey.parse("CTRL+SHIFT+ALT+T")

        self.assertEqual(hotkey, DEFAULT_TOGGLE_HOTKEY)
        self.assertEqual(str(hotkey), "CTRL+SHIFT+ALT+T")
        self.assertEqual(
            hotkey.to_display_string(),
            "Ctrl+Shift+Alt+T",
        )

    def test_function_key_is_supported(self):
        hotkey = Hotkey.parse("CTRL+F12")

        self.assertEqual(hotkey.key, "F12")
        self.assertTrue(hotkey.control)

    def test_windows_key_is_supported_as_modifier(self):
        hotkey = Hotkey.parse("WIN+SHIFT+F4")

        self.assertTrue(hotkey.windows)
        self.assertTrue(hotkey.shift)
        self.assertEqual(hotkey.key_code, 0x73)
        self.assertEqual(str(hotkey), "SHIFT+WIN+F4")

    def test_oem_keys_are_supported_by_virtual_key_code(self):
        expected_codes = {
            "CTRL+VK_BA": 0xBA,
            "CTRL+VK_BB": 0xBB,
            "CTRL+VK_BC": 0xBC,
            "CTRL+VK_BD": 0xBD,
            "CTRL+VK_BE": 0xBE,
            "CTRL+VK_BF": 0xBF,
            "CTRL+VK_C0": 0xC0,
            "CTRL+VK_DB": 0xDB,
            "CTRL+VK_DC": 0xDC,
            "CTRL+VK_DD": 0xDD,
            "CTRL+VK_DE": 0xDE,
        }
        for value, expected_code in expected_codes.items():
            with self.subTest(value=value):
                hotkey = Hotkey.parse(value)
                self.assertEqual(hotkey.key_code, expected_code)

    def test_key_can_be_created_from_any_usable_virtual_key_code(self):
        for key_code in (0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xDF, 0xE2):
            with self.subTest(key_code=key_code):
                key = Hotkey.key_from_code(key_code)
                hotkey = Hotkey(key=key, control=True)
                self.assertEqual(hotkey.key_code, key_code)

    def test_hotkey_requires_a_modifier(self):
        with self.assertRaises(ValueError):
            Hotkey.parse("T")

    def test_invalid_hotkeys_are_rejected(self):
        invalid_values = (
            "",
            "CTRL+",
            "CTRL+SHIFT",
            "CTRL+T+U",
            "CTRL+CTRL+T",
            "CTRL+F25",
            "CTRL+TAB",
            "CTRL+,",
            "CTRL+.",
            "CTRL+^",
            "CTRL+ß",
            "CTRL+´",
            "CTRL+<",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Hotkey.parse(value)


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
                toggle_window_hotkey=Hotkey.parse("CTRL+ALT+F8"),
                language="de",
                include_copied_text_in_clipboard_history=False,
                allow_copied_text_cloud_upload=False,
                hotstrings_enabled=False,
                preserve_hotstring_boundary=False,
                notify_hotstring_expansion=True,
            )

            store.save(settings)

            self.assertEqual(store.load(), settings)
            self.assertIn(
                "toggle_window = CTRL+ALT+F8",
                settings_file.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "language = de",
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
            self.assertTrue(settings.include_copied_text_in_clipboard_history)
            self.assertTrue(settings.allow_copied_text_cloud_upload)
            self.assertTrue(settings.hotstrings_enabled)
            self.assertTrue(settings.preserve_hotstring_boundary)
            self.assertFalse(settings.notify_hotstring_expansion)

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
