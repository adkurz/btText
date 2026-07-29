import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wx

from core.shortcuts import DEFAULT_TOGGLE_HOTKEY
from ui.settings_dialog import SettingsDialog


class SettingsDialogHotkeyRecordingTestCase(unittest.TestCase):
    @patch("ui.settings_dialog.hotkey_from_event")
    @patch("ui.settings_dialog.is_modifier_event", return_value=True)
    def test_modifier_event_keeps_recording(
        self,
        is_modifier,
        hotkey_from_event,
    ):
        dialog = SimpleNamespace(_recording=True)

        SettingsDialog._on_character(dialog, Mock())

        hotkey_from_event.assert_not_called()

    def test_tab_cancels_recording_and_continues_navigation(self):
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_TAB
        dialog = SimpleNamespace(
            _recording=True,
            _cancel_recording=Mock(),
        )

        SettingsDialog._on_character(dialog, event)

        dialog._cancel_recording.assert_called_once_with()
        event.Skip.assert_called_once_with()

    @patch(
        "ui.settings_dialog.format_hotkey",
        return_value="Ctrl+Shift+Alt+T",
    )
    @patch(
        "ui.settings_dialog.hotkey_from_event",
        return_value=DEFAULT_TOGGLE_HOTKEY,
    )
    @patch("ui.settings_dialog.is_modifier_event", return_value=False)
    def test_valid_event_updates_candidate_and_finishes_recording(
        self,
        is_modifier,
        hotkey_from_event,
        format_hotkey,
    ):
        event = Mock()
        event.GetKeyCode.return_value = ord("T")
        event.AltDown.return_value = False
        dialog = SimpleNamespace(
            _recording=True,
            _candidate_hotkey=None,
            hotkey_display=Mock(),
            _update_apply_button=Mock(),
            _finish_recording=Mock(),
        )

        SettingsDialog._on_character(dialog, event)

        self.assertEqual(dialog._candidate_hotkey, DEFAULT_TOGGLE_HOTKEY)
        dialog.hotkey_display.SetValue.assert_called_once_with(
            "Ctrl+Shift+Alt+T"
        )
        dialog._update_apply_button.assert_called_once_with()
        dialog._finish_recording.assert_called_once()
