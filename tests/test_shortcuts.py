import ast
import unittest
from pathlib import Path

from core.shortcuts import DEFAULT_TOGGLE_HOTKEY, Hotkey


class HotkeyTestCase(unittest.TestCase):
    def test_hotkey_round_trip(self):
        hotkey = Hotkey.parse("CTRL+SHIFT+ALT+T")

        self.assertEqual(hotkey, DEFAULT_TOGGLE_HOTKEY)
        self.assertEqual(str(hotkey), "CTRL+SHIFT+ALT+T")

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
        key_codes = (
            0xBA,
            0xBB,
            0xBC,
            0xBD,
            0xBE,
            0xBF,
            0xC0,
            0xDF,
            0xE2,
        )
        for key_code in key_codes:
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

    def test_model_has_no_platform_or_localization_imports(self):
        source_file = Path(__file__).resolve().parents[1] / "core" / "shortcuts.py"
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_roots.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )

        self.assertTrue({"ctypes", "i18n", "platform_support", "sys"}.isdisjoint(
            imported_roots
        ))
