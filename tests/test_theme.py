import ctypes
from ctypes import wintypes
import unittest
from unittest.mock import Mock, patch

import wx

from core.app_settings import APPEARANCE_DARK, APPEARANCE_LIGHT
from ui import theme


class ThemeSelectionTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def tearDown(self):
        theme._active_theme = None

    @patch("ui.theme.system_uses_dark_mode", return_value=True)
    def test_initialize_selects_dark_theme(self, system_uses_dark_mode):
        active_theme = theme.initialize()

        self.assertTrue(active_theme.dark)
        system_uses_dark_mode.assert_called_once_with()

    @patch("ui.theme.system_uses_dark_mode")
    def test_explicit_dark_does_not_query_system(self, system_uses_dark_mode):
        active_theme = theme.initialize(APPEARANCE_DARK)

        self.assertTrue(active_theme.dark)
        system_uses_dark_mode.assert_not_called()

    @patch("ui.theme.system_uses_dark_mode")
    def test_explicit_light_does_not_query_system(self, system_uses_dark_mode):
        active_theme = theme.initialize(APPEARANCE_LIGHT)

        self.assertFalse(active_theme.dark)
        system_uses_dark_mode.assert_not_called()

    @patch("ui.theme.system_uses_dark_mode", return_value=False)
    def test_initialize_selects_light_theme_for_light_system(
        self,
        system_uses_dark_mode,
    ):
        active_theme = theme.initialize()

        self.assertFalse(active_theme.dark)
        self.assertIs(active_theme, theme._LIGHT_THEME)

    @patch("ui.theme._apply_windows_title_bar")
    @patch("ui.theme._apply_to_window")
    def test_apply_colours_all_descendants(
        self,
        apply_to_window,
        apply_windows_title_bar,
    ):
        child = Mock(spec=wx.Window)
        child.GetChildren.return_value = []
        parent = Mock(spec=wx.Window)
        parent.GetChildren.return_value = [child]
        theme._active_theme = theme._DARK_THEME

        theme.apply(parent)

        self.assertEqual(apply_to_window.call_count, 2)
        apply_to_window.assert_any_call(parent, theme._DARK_THEME)
        apply_to_window.assert_any_call(child, theme._DARK_THEME)
        apply_windows_title_bar.assert_not_called()

    @patch("ui.theme._apply_windows_title_bar")
    def test_dark_theme_colours_real_wx_controls(self, apply_title_bar):
        frame = wx.Frame(None)
        panel = wx.Panel(frame)
        text_input = wx.TextCtrl(panel)
        theme._active_theme = theme._DARK_THEME
        try:
            theme.apply(frame)

            self.assertEqual(
                panel.GetBackgroundColour(),
                theme._DARK_THEME.window_background,
            )
            self.assertEqual(
                text_input.GetBackgroundColour(),
                theme._DARK_THEME.control_background,
            )
            self.assertEqual(
                text_input.GetForegroundColour(),
                theme._DARK_THEME.foreground,
            )
            apply_title_bar.assert_called_once_with(frame, True)
        finally:
            frame.Destroy()

    @patch("ui.theme.sys.platform", "win32")
    @patch("ui.theme.ctypes.windll")
    def test_windows_title_bar_uses_documented_windows_11_attribute(
        self,
        windll,
    ):
        window = Mock()
        window.GetHandle.return_value = 123

        theme._apply_windows_title_bar(window, True)

        call = windll.dwmapi.DwmSetWindowAttribute.call_args
        self.assertEqual(call.args[0].value, 123)
        self.assertEqual(
            call.args[1],
            theme.DWMWA_USE_IMMERSIVE_DARK_MODE,
        )
        self.assertEqual(call.args[3], ctypes.sizeof(wintypes.BOOL()))
        windll.dwmapi.DwmSetWindowAttribute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
