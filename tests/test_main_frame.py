import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app_settings import DEFAULT_TOGGLE_HOTKEY
from ui.main_frame import MainFrame


class ApplicationMenuTestCase(unittest.TestCase):
    def test_close_command_keeps_application_running(self):
        frame = SimpleNamespace(Close=Mock())

        MainFrame.on_hide_window(frame, Mock())

        frame.Close.assert_called_once_with()

    def test_exit_command_allows_complete_shutdown(self):
        frame = SimpleNamespace(allow_close=False, Close=Mock())

        MainFrame.on_exit_application(frame, Mock())

        self.assertTrue(frame.allow_close)
        frame.Close.assert_called_once_with()


class HotkeyLayoutChangeTestCase(unittest.TestCase):
    @patch("ui.main_frame._activate_keyboard_layout")
    @patch(
        "ui.main_frame._get_foreground_keyboard_layout",
        return_value=0x04090409,
    )
    def test_layout_change_re_registers_active_hotkey(
        self,
        get_keyboard_layout,
        activate_keyboard_layout,
    ):
        frame = SimpleNamespace(
            _hotkey_keyboard_layout=0x04070407,
            _hotkey_suspended=False,
            _registered_hotkey=DEFAULT_TOGGLE_HOTKEY,
            _unregister_hotkey=Mock(),
            _register_hotkey=Mock(),
        )

        MainFrame._on_hotkey_layout_timer(frame, Mock())

        self.assertEqual(frame._hotkey_keyboard_layout, 0x04090409)
        activate_keyboard_layout.assert_called_once_with(0x04090409)
        frame._unregister_hotkey.assert_called_once_with()
        frame._register_hotkey.assert_called_once_with(DEFAULT_TOGGLE_HOTKEY)

    @patch("ui.main_frame._activate_keyboard_layout")
    @patch(
        "ui.main_frame._get_foreground_keyboard_layout",
        return_value=0x04090409,
    )
    def test_suspended_hotkey_is_not_registered_during_layout_change(
        self,
        get_keyboard_layout,
        activate_keyboard_layout,
    ):
        frame = SimpleNamespace(
            _hotkey_keyboard_layout=0x04070407,
            _hotkey_suspended=True,
            _registered_hotkey=None,
            _unregister_hotkey=Mock(),
            _register_hotkey=Mock(),
        )

        MainFrame._on_hotkey_layout_timer(frame, Mock())

        activate_keyboard_layout.assert_called_once_with(0x04090409)
        frame._unregister_hotkey.assert_not_called()
        frame._register_hotkey.assert_not_called()

    @patch("ui.main_frame._activate_keyboard_layout")
    @patch(
        "ui.main_frame._get_foreground_keyboard_layout",
        return_value=0x04070407,
    )
    def test_unchanged_layout_keeps_registration(
        self,
        get_keyboard_layout,
        activate_keyboard_layout,
    ):
        frame = SimpleNamespace(
            _hotkey_keyboard_layout=0x04070407,
            _hotkey_suspended=False,
            _registered_hotkey=DEFAULT_TOGGLE_HOTKEY,
            _unregister_hotkey=Mock(),
            _register_hotkey=Mock(),
        )

        MainFrame._on_hotkey_layout_timer(frame, Mock())

        activate_keyboard_layout.assert_not_called()
        frame._unregister_hotkey.assert_not_called()
        frame._register_hotkey.assert_not_called()


if __name__ == "__main__":
    unittest.main()
