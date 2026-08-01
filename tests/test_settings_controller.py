import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from core.app_settings import APPEARANCE_DARK, AppSettings, SettingsError
from core.shortcuts import DEFAULT_TOGGLE_HOTKEY, Hotkey
from ui.settings_controller import SettingsController


class SettingsControllerTestCase(unittest.TestCase):
    def setUp(self):
        self.parent = Mock()
        self.store = Mock()
        self.global_hotkey = Mock()
        self.hotstrings = Mock()
        self.settings = AppSettings()
        self.controller = SettingsController(
            self.parent,
            self.store,
            self.settings,
            self.global_hotkey,
            self.hotstrings,
        )

    @patch("ui.settings_controller.wx.MessageBox")
    def test_save_failure_restores_previous_hotkey_and_settings(
        self,
        message_box,
    ):
        new_hotkey = Hotkey.parse("CTRL+ALT+F8")
        self.global_hotkey.register.side_effect = (True, True)
        self.store.save.side_effect = SettingsError(
            "settings_save_failed",
            "The settings file could not be saved: {reason}",
            reason=OSError("disk unavailable"),
        )

        changed = self.controller.apply(
            new_hotkey,
            self.settings.language,
            self.settings.appearance,
            self.settings.include_copied_text_in_clipboard_history,
            self.settings.allow_copied_text_cloud_upload,
            self.settings.hotstrings_enabled,
            self.settings.preserve_hotstring_boundary,
            self.settings.notify_hotstring_expansion,
        )

        self.assertFalse(changed)
        self.assertIs(self.controller.settings, self.settings)
        self.assertEqual(
            self.global_hotkey.register.call_args_list,
            [
                call(new_hotkey),
                call(self.settings.toggle_window_hotkey),
            ],
        )
        self.assertEqual(self.global_hotkey.unregister.call_count, 2)
        message_box.assert_called_once()

    def test_hotstring_start_failure_leaves_settings_unchanged(self):
        self.settings = AppSettings(hotstrings_enabled=False)
        self.controller = SettingsController(
            self.parent,
            self.store,
            self.settings,
            self.global_hotkey,
            self.hotstrings,
        )
        self.hotstrings.start.return_value = False

        changed = self.controller.apply(
            self.settings.toggle_window_hotkey,
            self.settings.language,
            self.settings.appearance,
            self.settings.include_copied_text_in_clipboard_history,
            self.settings.allow_copied_text_cloud_upload,
            True,
            self.settings.preserve_hotstring_boundary,
            self.settings.notify_hotstring_expansion,
        )

        self.assertFalse(changed)
        self.assertIs(self.controller.settings, self.settings)
        self.store.save.assert_not_called()
        self.global_hotkey.register.assert_not_called()
        self.global_hotkey.unregister.assert_not_called()

    def test_initial_hotstring_start_failure_can_be_retried_on_apply(self):
        self.hotstrings.start.side_effect = (False, True)

        self.assertFalse(self.controller.start_initial_hotstrings())
        changed = self.controller.apply(
            self.settings.toggle_window_hotkey,
            self.settings.language,
            self.settings.appearance,
            self.settings.include_copied_text_in_clipboard_history,
            self.settings.allow_copied_text_cloud_upload,
            self.settings.hotstrings_enabled,
            self.settings.preserve_hotstring_boundary,
            self.settings.notify_hotstring_expansion,
        )

        self.assertTrue(changed)
        self.assertEqual(self.hotstrings.start.call_count, 2)
        self.store.save.assert_called_once_with(self.controller.settings)

    def test_successful_initial_hotstring_start_is_not_repeated_on_apply(self):
        self.hotstrings.start.return_value = True

        self.assertTrue(self.controller.start_initial_hotstrings())
        changed = self.controller.apply(
            self.settings.toggle_window_hotkey,
            self.settings.language,
            self.settings.appearance,
            self.settings.include_copied_text_in_clipboard_history,
            self.settings.allow_copied_text_cloud_upload,
            self.settings.hotstrings_enabled,
            self.settings.preserve_hotstring_boundary,
            self.settings.notify_hotstring_expansion,
        )

        self.assertTrue(changed)
        self.hotstrings.start.assert_called_once_with()

    def test_initial_hotstrings_are_loaded_but_not_started_when_disabled(self):
        self.settings = AppSettings(hotstrings_enabled=False)
        self.controller = SettingsController(
            self.parent,
            self.store,
            self.settings,
            self.global_hotkey,
            self.hotstrings,
        )

        self.assertTrue(self.controller.start_initial_hotstrings())

        self.hotstrings.refresh.assert_called_once_with()
        self.hotstrings.start.assert_not_called()

    @patch("ui.settings_controller.wx.MessageBox")
    def test_hotkey_conflict_restores_old_binding_without_saving(
        self,
        message_box,
    ):
        new_hotkey = Hotkey.parse("CTRL+ALT+F8")
        self.global_hotkey.register.side_effect = (False, True)

        changed = self.controller.apply(
            new_hotkey,
            self.settings.language,
            self.settings.appearance,
            self.settings.include_copied_text_in_clipboard_history,
            self.settings.allow_copied_text_cloud_upload,
            self.settings.hotstrings_enabled,
            self.settings.preserve_hotstring_boundary,
            self.settings.notify_hotstring_expansion,
        )

        self.assertFalse(changed)
        self.assertIs(self.controller.settings, self.settings)
        self.assertEqual(
            self.global_hotkey.register.call_args_list,
            [
                call(new_hotkey),
                call(self.settings.toggle_window_hotkey),
            ],
        )
        self.global_hotkey.unregister.assert_called_once_with()
        self.store.save.assert_not_called()
        message_box.assert_called_once()

    def test_disabling_hotstrings_stops_hook_after_settings_are_saved(self):
        changed = self.controller.apply(
            self.settings.toggle_window_hotkey,
            self.settings.language,
            self.settings.appearance,
            self.settings.include_copied_text_in_clipboard_history,
            self.settings.allow_copied_text_cloud_upload,
            False,
            self.settings.preserve_hotstring_boundary,
            self.settings.notify_hotstring_expansion,
        )

        self.assertTrue(changed)
        self.assertFalse(self.controller.settings.hotstrings_enabled)
        self.store.save.assert_called_once_with(self.controller.settings)
        self.hotstrings.stop.assert_called_once_with()

    def test_changed_appearance_is_persisted_for_next_start(self):
        changed = self.controller.apply(
            self.settings.toggle_window_hotkey,
            self.settings.language,
            APPEARANCE_DARK,
            self.settings.include_copied_text_in_clipboard_history,
            self.settings.allow_copied_text_cloud_upload,
            self.settings.hotstrings_enabled,
            self.settings.preserve_hotstring_boundary,
            self.settings.notify_hotstring_expansion,
        )

        self.assertTrue(changed)
        self.assertEqual(self.controller.settings.appearance, APPEARANCE_DARK)
        self.store.save.assert_called_once_with(self.controller.settings)

    @patch("ui.settings_controller.wx.MessageBox")
    def test_resume_reports_failed_registration(self, message_box):
        self.global_hotkey.resume.return_value = False

        self.controller.resume_hotkey()

        self.global_hotkey.resume.assert_called_once_with(
            DEFAULT_TOGGLE_HOTKEY
        )
        message_box.assert_called_once()

    def test_database_file_is_saved_without_changing_other_settings(self):
        database_file = str(Path("selected.db").resolve())

        saved = self.controller.save_database_file(database_file)

        self.assertTrue(saved)
        self.assertEqual(
            self.controller.settings.database_file,
            database_file,
        )
        self.assertEqual(
            self.controller.settings.toggle_window_hotkey,
            self.settings.toggle_window_hotkey,
        )
        self.store.save.assert_called_once_with(self.controller.settings)

    @patch("ui.settings_controller.wx.MessageBox")
    def test_database_save_failure_keeps_current_settings(self, message_box):
        self.store.save.side_effect = SettingsError(
            "settings_save_failed",
            "The settings file could not be saved: {reason}",
            reason=OSError("disk unavailable"),
        )

        saved = self.controller.save_database_file(
            str(Path("selected.db").resolve())
        )

        self.assertFalse(saved)
        self.assertIs(self.controller.settings, self.settings)
        message_box.assert_called_once()


if __name__ == "__main__":
    unittest.main()
