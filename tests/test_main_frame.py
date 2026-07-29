import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.app_settings import AppSettings, SettingsError
from core.shortcuts import DEFAULT_TOGGLE_HOTKEY, Hotkey
from ui.main_frame import MainFrame


class ApplicationMenuTestCase(unittest.TestCase):
    def test_close_command_keeps_application_running(self):
        frame = SimpleNamespace(Close=Mock())

        MainFrame.on_hide_window(frame, Mock())

        frame.Close.assert_called_once_with()

    @patch("ui.main_frame.wx.MessageBox")
    @patch("ui.main_frame.datamodel.DataModel")
    @patch("ui.main_frame.select_database")
    def test_database_change_is_validated_and_saved_for_next_start(
        self,
        select_database,
        data_model,
        message_box,
    ):
        database_file = Path("selected.db").resolve()
        select_database.return_value = SimpleNamespace(
            path=database_file,
            create=False,
        )
        store = Mock()
        frame = SimpleNamespace(
            _settings=AppSettings(),
            _settings_store=store,
        )

        MainFrame.on_select_database(frame, Mock())

        data_model.assert_called_once_with(
            unittest.mock.ANY,
            database_file,
            allow_create=False,
        )
        data_model.return_value.close.assert_called_once_with()
        self.assertEqual(frame._settings.database_file, str(database_file))
        store.save.assert_called_once_with(frame._settings)
        message_box.assert_called_once()

    def test_exit_command_allows_complete_shutdown(self):
        frame = SimpleNamespace(allow_close=False, Close=Mock())

        MainFrame.on_exit_application(frame, Mock())

        self.assertTrue(frame.allow_close)
        frame.Close.assert_called_once_with()


class HotkeyLayoutChangeTestCase(unittest.TestCase):
    def test_resume_reports_failed_registration(self):
        binding = Mock()
        binding.resume.return_value = False
        frame = SimpleNamespace(
            _global_hotkey=binding,
            _settings=AppSettings(),
            _show_hotkey_registration_error=Mock(),
        )

        MainFrame._resume_hotkey(frame)

        binding.resume.assert_called_once_with(DEFAULT_TOGGLE_HOTKEY)
        frame._show_hotkey_registration_error.assert_called_once_with(
            DEFAULT_TOGGLE_HOTKEY
        )

    def test_layout_timer_delegates_to_binding(self):
        frame = SimpleNamespace(
            _global_hotkey=Mock(
                refresh_keyboard_layout=Mock(return_value=None)
            ),
            _show_hotkey_registration_error=Mock(),
        )

        MainFrame._on_hotkey_layout_timer(frame, Mock())

        frame._global_hotkey.refresh_keyboard_layout.assert_called_once_with()
        frame._show_hotkey_registration_error.assert_not_called()

    def test_layout_timer_reports_failed_registration(self):
        frame = SimpleNamespace(
            _global_hotkey=Mock(
                refresh_keyboard_layout=Mock(
                    return_value=DEFAULT_TOGGLE_HOTKEY
                )
            ),
            _show_hotkey_registration_error=Mock(),
        )

        MainFrame._on_hotkey_layout_timer(frame, Mock())

        frame._show_hotkey_registration_error.assert_called_once_with(
            DEFAULT_TOGGLE_HOTKEY
        )


class SettingsChangeTestCase(unittest.TestCase):
    @patch("ui.main_frame.wx.MessageBox")
    def test_save_failure_restores_previous_hotkey_and_settings(
        self,
        message_box,
    ):
        old_settings = AppSettings()
        new_hotkey = Hotkey.parse("CTRL+ALT+F8")
        store = Mock()
        store.save.side_effect = SettingsError(
            "settings_save_failed",
            "The settings file could not be saved: {reason}",
            reason=OSError("disk unavailable"),
        )
        frame = SimpleNamespace(
            _settings=old_settings,
            _settings_store=store,
            _hotstring_hook=Mock(),
            _register_hotkey=Mock(side_effect=(True, True)),
            _unregister_hotkey=Mock(),
        )

        changed = MainFrame._change_settings(
            frame,
            new_hotkey,
            old_settings.language,
            old_settings.include_copied_text_in_clipboard_history,
            old_settings.allow_copied_text_cloud_upload,
            old_settings.hotstrings_enabled,
            old_settings.preserve_hotstring_boundary,
            old_settings.notify_hotstring_expansion,
        )

        self.assertFalse(changed)
        self.assertIs(frame._settings, old_settings)
        self.assertEqual(
            frame._register_hotkey.call_args_list,
            [
                unittest.mock.call(new_hotkey, show_error=False),
                unittest.mock.call(
                    old_settings.toggle_window_hotkey,
                    show_error=False,
                ),
            ],
        )
        self.assertEqual(frame._unregister_hotkey.call_count, 2)
        message_box.assert_called_once()

    @patch("ui.main_frame.wx.MessageBox")
    def test_hotstring_start_failure_leaves_settings_unchanged(
        self,
        message_box,
    ):
        old_settings = AppSettings(hotstrings_enabled=False)
        hook = Mock()
        hook.start.side_effect = OSError("hook unavailable")
        frame = SimpleNamespace(
            _settings=old_settings,
            _settings_store=Mock(),
            _hotstring_hook=hook,
            _register_hotkey=Mock(),
            _unregister_hotkey=Mock(),
        )

        changed = MainFrame._change_settings(
            frame,
            old_settings.toggle_window_hotkey,
            old_settings.language,
            old_settings.include_copied_text_in_clipboard_history,
            old_settings.allow_copied_text_cloud_upload,
            True,
            old_settings.preserve_hotstring_boundary,
            old_settings.notify_hotstring_expansion,
        )

        self.assertFalse(changed)
        self.assertIs(frame._settings, old_settings)
        frame._settings_store.save.assert_not_called()
        frame._register_hotkey.assert_not_called()
        frame._unregister_hotkey.assert_not_called()
        message_box.assert_called_once()

    def test_disabling_hotstrings_stops_hook_after_settings_are_saved(self):
        old_settings = AppSettings(hotstrings_enabled=True)
        frame = SimpleNamespace(
            _settings=old_settings,
            _settings_store=Mock(),
            _hotstring_hook=Mock(),
            _register_hotkey=Mock(),
            _unregister_hotkey=Mock(),
        )

        changed = MainFrame._change_settings(
            frame,
            old_settings.toggle_window_hotkey,
            old_settings.language,
            old_settings.include_copied_text_in_clipboard_history,
            old_settings.allow_copied_text_cloud_upload,
            False,
            old_settings.preserve_hotstring_boundary,
            old_settings.notify_hotstring_expansion,
        )

        self.assertTrue(changed)
        self.assertFalse(frame._settings.hotstrings_enabled)
        frame._settings_store.save.assert_called_once_with(frame._settings)
        frame._hotstring_hook.stop.assert_called_once_with()


class ShutdownTestCase(unittest.TestCase):
    def test_explicit_exit_releases_process_wide_resources(self):
        event = Mock()
        frame = SimpleNamespace(
            allow_close=True,
            _hotkey_layout_timer=Mock(),
            _unregister_hotkey=Mock(),
            _hotstring_hook=Mock(),
            tray_icon=Mock(),
        )

        MainFrame.on_close(frame, event)

        frame._hotkey_layout_timer.Stop.assert_called_once_with()
        frame._unregister_hotkey.assert_called_once_with()
        frame._hotstring_hook.stop.assert_called_once_with()
        frame.tray_icon.RemoveIcon.assert_called_once_with()
        frame.tray_icon.Destroy.assert_called_once_with()
        event.Skip.assert_called_once_with()
        event.Veto.assert_not_called()


if __name__ == "__main__":
    unittest.main()
