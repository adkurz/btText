import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pymitter
import wx

from core.app_settings import AppSettings, SettingsStore
from core.datamodel import DataModel
from core.shortcuts import DEFAULT_TOGGLE_HOTKEY
from i18n import _
from ui.category_tree import CategoryTree
from ui.main_frame import MainFrame
from ui.snippet_list import SnippetList


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
        settings_controller = Mock()
        settings_controller.save_database_file.return_value = True
        frame = SimpleNamespace(
            _settings_controller=settings_controller,
        )

        MainFrame.on_select_database(frame, Mock())

        data_model.assert_called_once_with(
            unittest.mock.ANY,
            database_file,
            allow_create=False,
        )
        data_model.return_value.close.assert_called_once_with()
        settings_controller.save_database_file.assert_called_once_with(
            str(database_file)
        )
        message_box.assert_called_once()

    def test_exit_command_allows_complete_shutdown(self):
        frame = SimpleNamespace(allow_close=False, Close=Mock())

        MainFrame.on_exit_application(frame, Mock())

        self.assertTrue(frame.allow_close)
        frame.Close.assert_called_once_with()


class MainFrameConstructionTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)
        cls.app.SetAppName("btText")

    @patch("ui.main_frame.TrayIcon")
    @patch("ui.main_frame.SettingsController")
    @patch("ui.main_frame.HotstringController")
    @patch("ui.main_frame.PasteController")
    @patch("ui.main_frame.WxGlobalHotkeyBinding")
    def test_real_wx_frame_constructs_primary_views(
        self,
        global_hotkey_class,
        paste_controller_class,
        hotstring_controller_class,
        settings_controller_class,
        tray_icon_class,
    ):
        global_hotkey_class.return_value.hotkey_id = 1
        settings = AppSettings(hotstrings_enabled=False)
        settings_controller_class.return_value.settings = settings

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            events = pymitter.EventEmitter()
            model = DataModel(events, directory / "data.db")
            store = SettingsStore(directory / "settings.ini")
            frame = None
            try:
                frame = MainFrame(events, model, store, settings)

                self.assertIsInstance(frame.category_tree, CategoryTree)
                self.assertIsInstance(frame.snippet_list, SnippetList)
                self.assertIsNotNone(frame.GetMenuBar())
                self.assertIsNotNone(frame.GetStatusBar())
                self.assertEqual(frame.category_tree.GetName(), _("Categories"))
                self.assertEqual(
                    frame.snippet_list.GetName(),
                    _("Snippets in the selected category"),
                )
                (
                    settings_controller_class.return_value
                    .register_initial_hotkey.assert_called_once_with()
                )
                (
                    hotstring_controller_class.return_value.refresh
                    .assert_called_once_with()
                )
                (
                    hotstring_controller_class.return_value.start
                    .assert_not_called()
                )
                tray_icon_class.assert_called_once_with(frame)
            finally:
                if frame is not None:
                    frame.Destroy()
                    wx.YieldIfNeeded()
                model.close()


class HotkeyLayoutChangeTestCase(unittest.TestCase):
    def test_layout_timer_delegates_to_binding(self):
        frame = SimpleNamespace(
            _global_hotkey=Mock(
                refresh_keyboard_layout=Mock(return_value=None)
            ),
            _settings_controller=Mock(),
        )

        MainFrame._on_hotkey_layout_timer(frame, Mock())

        frame._global_hotkey.refresh_keyboard_layout.assert_called_once_with()
        (
            frame._settings_controller.show_hotkey_registration_error
            .assert_not_called()
        )

    def test_layout_timer_reports_failed_registration(self):
        frame = SimpleNamespace(
            _global_hotkey=Mock(
                refresh_keyboard_layout=Mock(
                    return_value=DEFAULT_TOGGLE_HOTKEY
                )
            ),
            _settings_controller=Mock(),
        )

        MainFrame._on_hotkey_layout_timer(frame, Mock())

        (
            frame._settings_controller.show_hotkey_registration_error
            .assert_called_once_with(DEFAULT_TOGGLE_HOTKEY)
        )


class ShutdownTestCase(unittest.TestCase):
    def test_explicit_exit_releases_process_wide_resources(self):
        event = Mock()
        frame = SimpleNamespace(
            allow_close=True,
            _hotkey_layout_timer=Mock(),
            _settings_controller=Mock(),
            _hotstring_controller=Mock(),
            tray_icon=Mock(),
        )

        MainFrame.on_close(frame, event)

        frame._hotkey_layout_timer.Stop.assert_called_once_with()
        frame._settings_controller.unregister_hotkey.assert_called_once_with()
        frame._hotstring_controller.stop.assert_called_once_with()
        frame.tray_icon.RemoveIcon.assert_called_once_with()
        frame.tray_icon.Destroy.assert_called_once_with()
        event.Skip.assert_called_once_with()
        event.Veto.assert_not_called()


if __name__ == "__main__":
    unittest.main()
