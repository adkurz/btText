import tempfile
import unittest
from pathlib import Path

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

    def test_function_key_is_supported(self):
        hotkey = Hotkey.parse("CTRL+F12")

        self.assertEqual(hotkey.key, "F12")
        self.assertTrue(hotkey.control)

    def test_german_oem_key_is_supported(self):
        hotkey = Hotkey.parse("CTRL+SHIFT+<")

        self.assertEqual(hotkey.key, "<")
        self.assertTrue(hotkey.control)
        self.assertTrue(hotkey.shift)
        self.assertEqual(str(hotkey), "CTRL+SHIFT+<")

    def test_windows_key_is_supported_as_modifier(self):
        hotkey = Hotkey.parse("WIN+SHIFT+F4")

        self.assertTrue(hotkey.windows)
        self.assertTrue(hotkey.shift)
        self.assertEqual(hotkey.key_code, 0x73)
        self.assertEqual(str(hotkey), "SHIFT+WIN+F4")

    def test_oem_keys_are_supported_by_virtual_key_code(self):
        expected_codes = {
            "CTRL+,": 0xBC,
            "CTRL+.": 0xBE,
            "CTRL+^": 0xC0,
            "CTRL+ß": 0xBD,
            "CTRL+´": 0xBB,
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
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Hotkey.parse(value)


class SettingsStoreTestCase(unittest.TestCase):
    def test_missing_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = SettingsStore(Path(temporary_directory) / "settings.ini")

            self.assertEqual(store.load(), AppSettings())

    def test_settings_are_saved_and_loaded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            store = SettingsStore(settings_file)
            settings = AppSettings(
                toggle_window_hotkey=Hotkey.parse("CTRL+ALT+F8")
            )

            store.save(settings)

            self.assertEqual(store.load(), settings)
            self.assertIn(
                "toggle_window = CTRL+ALT+F8",
                settings_file.read_text(encoding="utf-8"),
            )

    def test_invalid_file_raises_settings_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.ini"
            settings_file.write_text(
                "[hotkeys]\ntoggle_window = T\n",
                encoding="utf-8",
            )
            store = SettingsStore(settings_file)

            with self.assertRaises(SettingsError):
                store.load()


if __name__ == "__main__":
    unittest.main()
