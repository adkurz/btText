import unittest
from unittest.mock import Mock

import wx

from datamodel import Snippet
from ui.tray_icon import TrayIcon


class TrayIconNotificationTestCase(unittest.TestCase):
    def test_wx_exposes_native_taskbar_notification_api(self):
        self.assertTrue(hasattr(wx.adv.TaskBarIcon, "ShowBalloon"))

    def test_hotstring_notification_omits_snippet_content(self):
        tray_icon = Mock()
        snippet = Snippet(
            "Greeting",
            "Confidential expanded content",
            1,
            hotstring="mfg",
        )

        TrayIcon.show_hotstring_notification(tray_icon, snippet)

        tray_icon.ShowBalloon.assert_called_once()
        title, message, timeout, icon = tray_icon.ShowBalloon.call_args.args
        self.assertTrue(title)
        self.assertIn("mfg", message)
        self.assertIn("Greeting", message)
        self.assertNotIn("Confidential", message)
        self.assertEqual(timeout, 3000)
        self.assertEqual(icon, wx.ICON_INFORMATION)


class TrayIconExitTestCase(unittest.TestCase):
    def test_exit_uses_main_frame_shutdown_command(self):
        tray_icon = Mock()
        tray_icon._frame = Mock()
        event = Mock()

        TrayIcon.on_exit(tray_icon, event)

        tray_icon._frame.on_exit_application.assert_called_once_with(event)


if __name__ == "__main__":
    unittest.main()
