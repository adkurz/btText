import unittest
from unittest.mock import Mock, patch

import wx

from core.shortcuts import DEFAULT_TOGGLE_HOTKEY, Hotkey
from ui.global_hotkey import WxGlobalHotkeyBinding


class WxGlobalHotkeyBindingTestCase(unittest.TestCase):
    @patch(
        "ui.global_hotkey.get_foreground_keyboard_layout",
        return_value=0x04070407,
    )
    def setUp(self, get_keyboard_layout):
        self.window = Mock()
        self.binding = WxGlobalHotkeyBinding(self.window, hotkey_id=7)

    def test_register_translates_modifiers_and_remembers_success(self):
        hotkey = Hotkey.parse("CTRL+SHIFT+ALT+WIN+F4")
        self.window.RegisterHotKey.return_value = True

        self.assertTrue(self.binding.register(hotkey))

        self.window.RegisterHotKey.assert_called_once_with(
            7,
            wx.MOD_CONTROL | wx.MOD_SHIFT | wx.MOD_ALT | wx.MOD_WIN,
            0x73,
        )
        self.assertEqual(self.binding.registered_hotkey, hotkey)

    def test_failed_registration_is_not_remembered(self):
        self.window.RegisterHotKey.return_value = False

        self.assertFalse(self.binding.register(DEFAULT_TOGGLE_HOTKEY))

        self.assertIsNone(self.binding.registered_hotkey)

    def test_unregister_is_idempotent(self):
        self.window.RegisterHotKey.return_value = True
        self.binding.register(DEFAULT_TOGGLE_HOTKEY)

        self.binding.unregister()
        self.binding.unregister()

        self.window.UnregisterHotKey.assert_called_once_with(7)
        self.assertIsNone(self.binding.registered_hotkey)

    def test_suspend_and_resume_restore_hotkey(self):
        self.window.RegisterHotKey.return_value = True
        self.binding.register(DEFAULT_TOGGLE_HOTKEY)

        self.binding.suspend()
        self.assertIsNone(self.binding.registered_hotkey)
        self.assertTrue(self.binding.resume(DEFAULT_TOGGLE_HOTKEY))

        self.assertEqual(
            self.binding.registered_hotkey,
            DEFAULT_TOGGLE_HOTKEY,
        )
        self.assertEqual(self.window.RegisterHotKey.call_count, 2)

    def test_resume_reports_failed_restoration(self):
        self.binding.suspend()
        self.window.RegisterHotKey.return_value = False

        self.assertFalse(self.binding.resume(DEFAULT_TOGGLE_HOTKEY))

        self.assertIsNone(self.binding.registered_hotkey)

    @patch("ui.global_hotkey.activate_keyboard_layout")
    @patch(
        "ui.global_hotkey.get_foreground_keyboard_layout",
        return_value=0x04090409,
    )
    def test_layout_change_re_registers_active_hotkey(
        self,
        get_keyboard_layout,
        activate_keyboard_layout,
    ):
        self.window.RegisterHotKey.return_value = True
        self.binding.register(DEFAULT_TOGGLE_HOTKEY)

        failed_hotkey = self.binding.refresh_keyboard_layout()

        self.assertIsNone(failed_hotkey)
        activate_keyboard_layout.assert_called_once_with(0x04090409)
        self.window.UnregisterHotKey.assert_called_once_with(7)
        self.assertEqual(self.window.RegisterHotKey.call_count, 2)

    @patch("ui.global_hotkey.activate_keyboard_layout")
    @patch(
        "ui.global_hotkey.get_foreground_keyboard_layout",
        return_value=0x04090409,
    )
    def test_layout_change_returns_hotkey_when_re_registration_fails(
        self,
        get_keyboard_layout,
        activate_keyboard_layout,
    ):
        self.window.RegisterHotKey.side_effect = (True, False)
        self.binding.register(DEFAULT_TOGGLE_HOTKEY)

        failed_hotkey = self.binding.refresh_keyboard_layout()

        self.assertEqual(failed_hotkey, DEFAULT_TOGGLE_HOTKEY)
        self.assertIsNone(self.binding.registered_hotkey)

    @patch("ui.global_hotkey.activate_keyboard_layout")
    @patch(
        "ui.global_hotkey.get_foreground_keyboard_layout",
        return_value=0x04090409,
    )
    def test_suspended_binding_only_activates_changed_layout(
        self,
        get_keyboard_layout,
        activate_keyboard_layout,
    ):
        self.binding.suspend()

        self.assertIsNone(self.binding.refresh_keyboard_layout())

        activate_keyboard_layout.assert_called_once_with(0x04090409)
        self.window.RegisterHotKey.assert_not_called()

    @patch("ui.global_hotkey.activate_keyboard_layout")
    @patch(
        "ui.global_hotkey.get_foreground_keyboard_layout",
        return_value=0x04070407,
    )
    def test_unchanged_layout_does_nothing(
        self,
        get_keyboard_layout,
        activate_keyboard_layout,
    ):
        self.assertIsNone(self.binding.refresh_keyboard_layout())

        activate_keyboard_layout.assert_not_called()
        self.window.RegisterHotKey.assert_not_called()
