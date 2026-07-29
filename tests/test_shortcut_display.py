import unittest
from unittest.mock import patch

from core.shortcuts import Hotkey
from ui.shortcut_display import format_hotkey


class ShortcutDisplayTestCase(unittest.TestCase):
    def test_formats_modifiers_and_main_key(self):
        hotkey = Hotkey.parse("CTRL+SHIFT+ALT+WIN+VK_BA")

        with patch(
            "ui.shortcut_display.get_key_label",
            return_value="Ö",
        ):
            self.assertEqual(format_hotkey(hotkey), "Ctrl+Shift+Alt+Win+Ö")
