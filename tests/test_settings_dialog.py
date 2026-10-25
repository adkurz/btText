import unittest
import dataclasses
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import wx

from core.app_settings import APPEARANCE_DARK, AppSettings
from core.shortcuts import DEFAULT_TOGGLE_HOTKEY, Hotkey
from ui.settings_dialog import SettingsDialog


class SettingsDialogTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def _create_dialog(self, settings, apply_settings):
        dialog = SettingsDialog(
            None, settings, ("en", "de"), apply_settings, Mock(), Mock()
        )
        self.addCleanup(lambda: dialog.Destroy() if dialog else None)
        return dialog

    def _record_hotkey(self, dialog, hotkey):
        dialog._start_recording(Mock())
        event = Mock()
        event.GetKeyCode.return_value = ord("T")
        event.AltDown.return_value = False
        with (
            patch("ui.settings_dialog.hotkey_from_event", return_value=hotkey),
            patch("ui.settings_dialog.is_modifier_event", return_value=False),
        ):
            dialog._on_character(event)

    def _run_modal(self, dialog, action):
        errors = []

        def run_action():
            try:
                action()
            except BaseException as error:
                errors.append(error)
                dialog.EndModal(wx.ID_ABORT)

        timer = wx.CallLater(50, run_action)
        timeout = wx.CallLater(2000, dialog.EndModal, wx.ID_ABORT)
        try:
            result = dialog.ShowModal()
        finally:
            timer.Stop()
            timeout.Stop()
        if errors:
            raise errors[0]
        return result

    def test_each_control_can_revert_to_the_unchanged_settings(self):
        cases = (
            ("language_choice", "_on_language_changed", "language", "en", 1),
            ("appearance_choice", "_on_appearance_changed", "appearance", APPEARANCE_DARK, 2),
            ("clipboard_history_checkbox", "_on_clipboard_history_changed", "include_copied_text_in_clipboard_history", False, None),
            ("cloud_clipboard_checkbox", "_on_cloud_clipboard_changed", "allow_copied_text_cloud_upload", False, None),
            ("hotstrings_checkbox", "_on_hotstrings_changed", "hotstrings_enabled", False, None),
            ("preserve_hotstring_boundary_checkbox", "_on_preserve_hotstring_boundary_changed", "preserve_hotstring_boundary", False, None),
            ("notify_hotstring_expansion_checkbox", "_on_notify_hotstring_expansion_changed", "notify_hotstring_expansion", True, None),
            ("play_hotstring_sound_checkbox", "_on_play_hotstring_sound_changed", "play_hotstring_sound", True, None),
        )
        settings = AppSettings(database_file="selected.db")
        for control_name, handler_name, field, value, selection in cases:
            with self.subTest(field=field):
                apply_settings = Mock(return_value=True)
                dialog = self._create_dialog(settings, apply_settings)
                control = getattr(dialog, control_name)
                handler = getattr(dialog, handler_name)
                if selection is None:
                    original = control.GetValue()
                    control.SetValue(value)
                else:
                    original = control.GetSelection()
                    control.SetSelection(selection)
                handler(Mock())
                self.assertTrue(dialog.apply_button.IsEnabled())
                self.assertEqual(
                    dialog._draft_settings, dataclasses.replace(settings, **{field: value})
                )
                if selection is None:
                    control.SetValue(original)
                else:
                    control.SetSelection(original)
                handler(Mock())
                self.assertFalse(dialog.apply_button.IsEnabled())
                self.assertTrue(dialog._apply())
                apply_settings.assert_not_called()

        apply_settings = Mock(return_value=True)
        dialog = self._create_dialog(settings, apply_settings)
        self._record_hotkey(dialog, Hotkey.parse("CTRL+ALT+F8"))
        self.assertTrue(dialog.apply_button.IsEnabled())
        self._record_hotkey(dialog, settings.toggle_window_hotkey)
        self.assertFalse(dialog.apply_button.IsEnabled())
        self.assertTrue(dialog._apply())
        apply_settings.assert_not_called()

    def test_apply_passes_one_complete_snapshot_that_later_edits_cannot_change(self):
        settings = AppSettings(database_file="selected.db")
        apply_settings = Mock(return_value=True)
        dialog = self._create_dialog(settings, apply_settings)
        dialog.language_choice.SetSelection(dialog._language_values.index("de"))
        dialog._on_language_changed(Mock())
        dialog.appearance_choice.SetSelection(2)
        dialog._on_appearance_changed(Mock())
        for control, handler, value in (
            (dialog.clipboard_history_checkbox, dialog._on_clipboard_history_changed, False),
            (dialog.cloud_clipboard_checkbox, dialog._on_cloud_clipboard_changed, False),
            (dialog.hotstrings_checkbox, dialog._on_hotstrings_changed, False),
            (dialog.preserve_hotstring_boundary_checkbox, dialog._on_preserve_hotstring_boundary_changed, False),
            (dialog.notify_hotstring_expansion_checkbox, dialog._on_notify_hotstring_expansion_changed, True),
            (dialog.play_hotstring_sound_checkbox, dialog._on_play_hotstring_sound_changed, True),
        ):
            control.SetValue(value)
            handler(Mock())
        hotkey = Hotkey.parse("CTRL+ALT+F8")
        self._record_hotkey(dialog, hotkey)
        expected = dataclasses.replace(
            settings, toggle_window_hotkey=hotkey, language="de",
            appearance=APPEARANCE_DARK,
            include_copied_text_in_clipboard_history=False,
            allow_copied_text_cloud_upload=False, hotstrings_enabled=False,
            preserve_hotstring_boundary=False, notify_hotstring_expansion=True,
            play_hotstring_sound=True,
        )

        self.assertTrue(dialog._apply())

        apply_settings.assert_called_once_with(expected)
        self.assertFalse(dialog.apply_button.IsEnabled())
        dialog.play_hotstring_sound_checkbox.SetValue(False)
        dialog._on_play_hotstring_sound_changed(Mock())
        self.assertTrue(dialog.apply_button.IsEnabled())
        self.assertEqual(apply_settings.call_args.args, (expected,))
        self.assertEqual(dialog._current_settings, expected)
        self.assertEqual(settings, AppSettings(database_file="selected.db"))

    def test_failed_ok_keeps_draft_open_and_retry_applies_the_same_values(self):
        settings = AppSettings(database_file="selected.db")
        apply_settings = Mock(side_effect=(False, True))
        dialog = self._create_dialog(settings, apply_settings)
        dialog.appearance_choice.SetSelection(2)
        dialog._on_appearance_changed(Mock())
        dialog.cloud_clipboard_checkbox.SetValue(False)
        dialog._on_cloud_clipboard_changed(Mock())
        draft = dataclasses.replace(
            settings, appearance=APPEARANCE_DARK, allow_copied_text_cloud_upload=False
        )

        def retry_after_failure():
            dialog._on_ok(Mock())
            self.assertTrue(dialog.IsModal())
            self.assertTrue(dialog.apply_button.IsEnabled())
            self.assertEqual(dialog._current_settings, settings)
            self.assertEqual(dialog._draft_settings, draft)
            self.assertEqual(dialog.appearance_choice.GetSelection(), 2)
            self.assertFalse(dialog.cloud_clipboard_checkbox.GetValue())
            dialog._on_ok(Mock())

        self.assertEqual(self._run_modal(dialog, retry_after_failure), wx.ID_OK)
        self.assertEqual(apply_settings.call_args_list, [call(draft), call(draft)])
        self.assertEqual(dialog._current_settings, draft)

    def test_cancel_discards_pending_changes_and_retains_an_earlier_apply(self):
        for apply_first in (False, True):
            with self.subTest(apply_first=apply_first):
                settings = AppSettings()
                apply_settings = Mock(return_value=True)
                dialog = self._create_dialog(settings, apply_settings)

                def cancel_changes():
                    dialog.appearance_choice.SetSelection(2)
                    dialog._on_appearance_changed(Mock())
                    if apply_first:
                        dialog._on_apply(Mock())
                    dialog.hotstrings_checkbox.SetValue(False)
                    dialog._on_hotstrings_changed(Mock())
                    dialog._start_recording(Mock())
                    dialog.Close()

                self.assertEqual(self._run_modal(dialog, cancel_changes), wx.ID_CANCEL)
                if apply_first:
                    apply_settings.assert_called_once_with(
                        dataclasses.replace(settings, appearance=APPEARANCE_DARK)
                    )
                else:
                    apply_settings.assert_not_called()
                dialog.Destroy()
                dialog._end_recording.assert_called_once_with()

    def test_design_page_selects_and_reports_appearance(self):
        apply_settings = Mock(return_value=True)
        dialog = SettingsDialog(
            None,
            AppSettings(play_hotstring_sound=True),
            ("en",),
            apply_settings,
            Mock(),
            Mock(),
        )
        try:
            dialog.appearance_choice.SetSelection(2)
            dialog._on_appearance_changed(Mock())

            self.assertEqual(dialog._draft_settings.appearance, APPEARANCE_DARK)
            self.assertTrue(dialog.apply_button.IsEnabled())
            self.assertTrue(dialog._apply())
            self.assertEqual(apply_settings.call_args.args[0].appearance, APPEARANCE_DARK)
        finally:
            dialog.Destroy()

    def test_hotstring_sound_setting_is_reported(self):
        apply_settings = Mock(return_value=True)
        dialog = SettingsDialog(
            None,
            AppSettings(play_hotstring_sound=True),
            ("en",),
            apply_settings,
            Mock(),
            Mock(),
        )
        try:
            dialog.play_hotstring_sound_checkbox.SetValue(False)
            dialog._on_play_hotstring_sound_changed(Mock())

            self.assertTrue(dialog.apply_button.IsEnabled())
            self.assertTrue(dialog._apply())
            self.assertFalse(apply_settings.call_args.args[0].play_hotstring_sound)
        finally:
            dialog.Destroy()

    def test_use_default_retries_unchanged_hotkey_on_apply(self):
        apply_settings = Mock(return_value=False)
        dialog = SettingsDialog(
            None,
            AppSettings(play_hotstring_sound=True),
            ("en",),
            apply_settings,
            Mock(),
            Mock(),
        )
        try:
            dialog._use_default(Mock())

            self.assertTrue(dialog.apply_button.IsEnabled())
            self.assertFalse(dialog._apply())
            apply_settings.assert_called_once()
        finally:
            dialog.Destroy()


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
            _draft_settings=AppSettings(
                toggle_window_hotkey=Hotkey.parse("CTRL+ALT+F8")
            ),
            hotkey_display=Mock(),
            _update_apply_button=Mock(),
            _finish_recording=Mock(),
        )

        SettingsDialog._on_character(dialog, event)

        self.assertEqual(dialog._draft_settings.toggle_window_hotkey, DEFAULT_TOGGLE_HOTKEY)
        dialog.hotkey_display.SetValue.assert_called_once_with("Ctrl+Shift+Alt+T")
        dialog._update_apply_button.assert_called_once_with()
        dialog._finish_recording.assert_called_once()
