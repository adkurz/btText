import unittest
from unittest.mock import Mock

import wx

from core.app_settings import APPEARANCE_DARK, APPEARANCE_LIGHT, APPEARANCE_SYSTEM
from ui import theme


class ThemeSelectionTestCase(unittest.TestCase):
    def test_apply_to_app_requests_native_dark_appearance(self):
        app = Mock()

        theme.apply_to_app(app, APPEARANCE_DARK)

        app.SetAppearance.assert_called_once_with(wx.PyApp.Appearance.Dark)

    def test_apply_to_app_requests_native_light_appearance(self):
        app = Mock()

        theme.apply_to_app(app, APPEARANCE_LIGHT)

        app.SetAppearance.assert_called_once_with(wx.PyApp.Appearance.Light)

    def test_apply_to_app_requests_native_system_appearance(self):
        app = Mock()

        theme.apply_to_app(app, APPEARANCE_SYSTEM)

        app.SetAppearance.assert_called_once_with(wx.PyApp.Appearance.System)


if __name__ == "__main__":
    unittest.main()
