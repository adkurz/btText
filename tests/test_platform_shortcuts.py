import unittest
from unittest.mock import patch

from core.shortcuts import Hotkey
from platform_support import shortcuts


class WindowsShortcutLabelTestCase(unittest.TestCase):
    def test_portable_key_name_does_not_require_windows_lookup(self):
        hotkey = Hotkey.parse("CTRL+F12")

        with patch.object(
            shortcuts.windll.user32,
            "MapVirtualKeyW",
        ) as map_virtual_key:
            self.assertEqual(shortcuts.get_key_label(hotkey), "F12")

        map_virtual_key.assert_not_called()

    def test_oem_key_uses_active_windows_layout_label(self):
        hotkey = Hotkey.parse("CTRL+VK_BA")

        def set_key_name(_key_data, buffer, _length):
            buffer.value = "Ö"
            return 1

        with (
            patch.object(
                shortcuts.windll.user32,
                "MapVirtualKeyW",
                return_value=0x27,
            ),
            patch.object(
                shortcuts.windll.user32,
                "GetKeyNameTextW",
                side_effect=set_key_name,
            ),
        ):
            self.assertEqual(shortcuts.get_key_label(hotkey), "Ö")

    def test_oem_key_falls_back_to_stored_name(self):
        hotkey = Hotkey.parse("CTRL+VK_BA")

        with (
            patch.object(
                shortcuts.windll.user32,
                "MapVirtualKeyW",
                return_value=0x27,
            ),
            patch.object(
                shortcuts.windll.user32,
                "GetKeyNameTextW",
                return_value=0,
            ),
        ):
            self.assertEqual(shortcuts.get_key_label(hotkey), "VK_BA")
