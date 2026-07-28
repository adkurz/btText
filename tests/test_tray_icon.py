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


if __name__ == "__main__":
    unittest.main()
