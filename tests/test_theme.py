import unittest
from unittest.mock import Mock, patch

import wx

from core.app_settings import APPEARANCE_DARK, APPEARANCE_LIGHT, APPEARANCE_SYSTEM
from ui import theme


class ThemeSelectionTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def tearDown(self):
        theme._active_theme = None

    @patch("ui.theme.wx.SystemSettings.GetAppearance")
    def test_apply_to_app_requests_native_dark_appearance(self, get_appearance):
        app = Mock()
        get_appearance.return_value.IsDark.return_value = True

        theme.apply_to_app(app, APPEARANCE_DARK)

        app.SetAppearance.assert_called_once_with(wx.PyApp.Appearance.Dark)
        self.assertIs(theme.get_active_theme(), theme._DARK_THEME)

    @patch("ui.theme.wx.SystemSettings.GetAppearance")
    def test_apply_to_app_requests_native_light_appearance(self, get_appearance):
        app = Mock()
        get_appearance.return_value.IsDark.return_value = False

        theme.apply_to_app(app, APPEARANCE_LIGHT)

        app.SetAppearance.assert_called_once_with(wx.PyApp.Appearance.Light)
        self.assertIs(theme.get_active_theme(), theme._LIGHT_THEME)

    @patch("ui.theme.wx.SystemSettings.GetAppearance")
    def test_apply_to_app_requests_native_system_appearance(self, get_appearance):
        app = Mock()
        get_appearance.return_value.IsDark.return_value = True

        theme.apply_to_app(app, APPEARANCE_SYSTEM)

        app.SetAppearance.assert_called_once_with(wx.PyApp.Appearance.System)
        get_appearance.assert_called_once_with()
        get_appearance.return_value.IsDark.assert_called_once_with()
        self.assertIs(theme.get_active_theme(), theme._DARK_THEME)

    @patch("ui.theme._apply_to_window")
    def test_apply_colours_all_descendants(
        self,
        apply_to_window,
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

    def test_dark_theme_colours_real_wx_controls(self):
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
        finally:
            frame.Destroy()


if __name__ == "__main__":
    unittest.main()
