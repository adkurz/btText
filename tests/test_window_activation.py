"""Native activation must preserve the window placement of insertion targets."""

import unittest
from unittest.mock import Mock, patch

import wx

from core.hotstrings import HotstringExpansionError
from platform_support import (
    clipboard_paste,
    hotstring_expansion,
    keyboard_input,
    windows,
)


class NativeInputFieldSurvivalTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def test_replacement_rejects_lost_fields_but_allows_unreported_focus(self):
        for field_state in ("destroyed", "reparented", "unreported"):
            with self.subTest(field_state=field_state):
                target = wx.Frame(None)
                other = wx.Frame(None)
                try:
                    original_field = wx.TextCtrl(target, value=";hi")
                    other_field = wx.TextCtrl(target, value="Keep this text")
                    identity = windows.get_window_identity(target.GetHandle())
                    self.assertIsNotNone(identity)
                    focus_handle = original_field.GetHandle()
                    self.assertTrue(windows.user32.IsChild(identity.handle, focus_handle))
                    if field_state == "destroyed":
                        original_field.Destroy()
                        wx.Yield()
                        self.assertFalse(windows.is_valid_window(focus_handle))
                    elif field_state == "reparented":
                        self.assertTrue(original_field.Reparent(other))
                        self.assertTrue(windows.is_valid_window(focus_handle))
                        self.assertFalse(windows.user32.IsChild(identity.handle, focus_handle))
                    else:
                        focus_handle = None
                    session = Mock()
                    # Use real HWND ownership and child checks, while avoiding
                    # foreground restrictions and all real clipboard/key input.
                    with (
                        patch.object(windows, "activate_window", return_value=True),
                        patch.object(keyboard_input, "send_hotstring_replacement") as replace,
                    ):
                        if field_state == "unreported":
                            hotstring_expansion.expand_hotstring(
                                identity, "Expanded", 3, 32, session=session,
                                target_focus=focus_handle,
                            )
                            replace.assert_called_once_with(3, 32)
                            session.prepare.return_value.restore_clipboard.assert_not_called()
                        else:
                            with self.assertRaises(HotstringExpansionError):
                                hotstring_expansion.expand_hotstring(
                                    identity, "Expanded", 3, 32, session=session,
                                    target_focus=focus_handle,
                                )
                            replace.assert_not_called()
                            session.prepare.return_value.restore_clipboard.assert_called_once_with()
                    self.assertEqual(other_field.GetValue(), "Keep this text")
                finally:
                    target.Destroy()
                    other.Destroy()
                    wx.Yield()


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
