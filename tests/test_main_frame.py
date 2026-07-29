import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.app_settings import AppSettings
from core.shortcuts import DEFAULT_TOGGLE_HOTKEY
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


if __name__ == "__main__":
    unittest.main()
