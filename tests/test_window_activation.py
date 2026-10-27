"""Native activation must preserve the window placement of insertion targets."""

import unittest
from unittest.mock import Mock, patch

import wx

from platform_support import (
    clipboard_paste,
    hotstring_expansion,
    keyboard_input,
    windows,
)


class NativeInsertionWindowPlacementTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def test_insertion_preserves_maximized_target(self):
        self._check_insertion_window_state("maximized")

    def test_insertion_preserves_normal_target_geometry(self):
        self._check_insertion_window_state("normal")

    def test_insertion_restores_minimized_target(self):
        self._check_insertion_window_state("minimized")

    def _check_insertion_window_state(self, state):
        for operation in ("paste", "hotstring"):
            with self.subTest(state=state, operation=operation):
                target = wx.Frame(
                    None,
                    title="Insertion window state regression",
                    pos=(100, 100),
                    size=(480, 320),
                )
                try:
                    target.Show()
                    wx.Yield()
                    if state == "maximized":
                        target.Maximize()
                    wx.Yield()
                    self.assertEqual(target.IsMaximized(), state == "maximized")
                    position = tuple(target.GetPosition())
                    size = tuple(target.GetSize())
                    identity = windows.get_window_identity(target.GetHandle())
                    self.assertIsNotNone(identity)
                    if state == "minimized":
                        target.Iconize()
                        wx.Yield()
                        self.assertTrue(target.IsIconized())
                    # Keep native window state calls, but simulate foreground
                    # permission so placement checks also work when Windows
                    # denies focus to the test runner. Isolate clipboard/input.
                    session = Mock()
                    with (
                        patch.object(
                            windows, "get_foreground_window",
                            return_value=identity.handle,
                        ),
                        patch.object(keyboard_input, "send_ctrl_v") as paste,
                        patch.object(
                            keyboard_input, "send_hotstring_replacement",
                        ) as replace,
                    ):
                        if operation == "paste":
                            pending = clipboard_paste.paste_text(
                                identity, "Expanded", session=session,
                            )
                            paste.assert_called_once_with()
                        else:
                            pending = hotstring_expansion.expand_hotstring(
                                identity, "Expanded", 1, None, session=session,
                            )
                            replace.assert_called_once_with(1, None)
                    self.assertIs(pending, session.prepare.return_value)
                    wx.Yield()
                    self.assertFalse(target.IsIconized())
                    self.assertEqual(target.IsMaximized(), state == "maximized")
                    self.assertEqual(tuple(target.GetPosition()), position)
                    self.assertEqual(tuple(target.GetSize()), size)
                finally:
                    target.Destroy()
                    wx.Yield()


if __name__ == "__main__":
    unittest.main()
