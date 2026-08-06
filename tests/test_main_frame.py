import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wx

from core.app_settings import AppSettings, SettingsStore
from core.datamodel import DataModel
from core.events import EventEmitter
from core.shortcuts import DEFAULT_TOGGLE_HOTKEY
from i18n import _
from ui.category_tree import CategoryTree
from ui.main_frame import MainFrame
from ui.snippet_list import SnippetList


class ApplicationMenuTestCase(unittest.TestCase):
    @patch("ui.main_frame.wx.MessageBox")
    @patch("ui.main_frame.open_log_directory")
    def test_log_directory_command_opens_directory(
        self,
        open_log_directory_mock,
        message_box,
    ):
        MainFrame.on_open_log_directory(SimpleNamespace(), Mock())

        open_log_directory_mock.assert_called_once_with()
        message_box.assert_not_called()

    @patch("ui.main_frame.wx.MessageBox")
    @patch(
        "ui.main_frame.open_log_directory",
        side_effect=OSError("unavailable"),
    )
    def test_log_directory_command_reports_opening_error(
        self,
        open_log_directory_mock,
        message_box,
    ):
        frame = SimpleNamespace()

        MainFrame.on_open_log_directory(frame, Mock())

        open_log_directory_mock.assert_called_once_with()
        message_box.assert_called_once()

    @patch("ui.main_frame.wx.MessageBox")
    @patch("ui.main_frame.open_manual")
    def test_manual_command_opens_localized_documentation(
        self, open_manual_mock, message_box
    ):
        MainFrame.on_open_manual(SimpleNamespace(), Mock())

        open_manual_mock.assert_called_once_with()
        message_box.assert_not_called()

    @patch("ui.main_frame.wx.MessageBox")
    @patch("ui.main_frame.open_manual", side_effect=FileNotFoundError("missing"))
    def test_manual_command_reports_opening_error(self, open_manual_mock, message_box):
        frame = SimpleNamespace()

        MainFrame.on_open_manual(frame, Mock())

        open_manual_mock.assert_called_once_with()
        message_box.assert_called_once()

    @patch("ui.main_frame.wx.MessageBox")
    @patch("ui.main_frame.open_changelog")
    def test_changelog_command_opens_localized_documentation(
        self, open_changelog_mock, message_box
    ):
        MainFrame.on_open_changelog(SimpleNamespace(), Mock())

        open_changelog_mock.assert_called_once_with()
        message_box.assert_not_called()

    @patch("ui.main_frame.wx.MessageBox")
    @patch("ui.main_frame.open_changelog", side_effect=FileNotFoundError("missing"))
    def test_changelog_command_reports_opening_error(
        self, open_changelog_mock, message_box
    ):
        frame = SimpleNamespace()

        MainFrame.on_open_changelog(frame, Mock())

        open_changelog_mock.assert_called_once_with()
        message_box.assert_called_once()

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
        settings = AppSettings(
            database_file=str(Path("chosen-snippets.db").resolve()),
            hotstrings_enabled=False,
        )
        settings_controller_class.return_value.settings = settings

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            events = EventEmitter()
            model = DataModel(events, directory / "data.db")
            store = SettingsStore(directory / "settings.ini")
            frame = None
            try:
                frame = MainFrame(events, model, store, settings)
                wx.YieldIfNeeded()

                self.assertIsInstance(frame.category_tree, CategoryTree)
                self.assertIsInstance(frame.snippet_list, SnippetList)
                self.assertEqual(
                    frame.GetTitle(),
                    "btText – chosen-snippets.db",
                )
                self.assertIsNotNone(frame.GetMenuBar())
                self.assertIsNotNone(frame.GetStatusBar())
                self.assertFalse(frame.IsShown())
                exit_item = frame.GetMenuBar().FindItemById(wx.ID_EXIT)
                self.assertEqual(exit_item.GetItemLabel(), _("E&xit\tCtrl+Q"))
                self.assertEqual(frame.category_tree.GetName(), _("Categories"))
                self.assertEqual(
                    frame.snippet_list.GetName(),
                    _("Snippets in the selected category"),
                )
                (
                    settings_controller_class.return_value.register_initial_hotkey.assert_called_once_with()
                )
                (
                    settings_controller_class.return_value.start_initial_hotstrings.assert_called_once_with()
                )
                tray_icon_class.assert_called_once_with(frame)
            finally:
                if frame is not None:
                    frame.Destroy()
                    wx.YieldIfNeeded()
                model.close()

    def test_hidden_frame_is_shown_without_activation_before_being_hidden(self):
        calls = []
        frame = SimpleNamespace(
            ShowWithoutActivating=lambda: calls.append("show"),
            Hide=lambda: calls.append("hide"),
        )

        MainFrame._initialize_hidden_frame(frame)

        self.assertEqual(calls, ["show", "hide"])


class HotkeyLayoutChangeTestCase(unittest.TestCase):
    def test_show_and_focus_sets_target_before_showing_frame(self):
        category_tree = Mock()
        frame = SimpleNamespace(
            Show=Mock(),
            Iconize=Mock(),
            _last_focused_control=None,
            category_tree=category_tree,
            _pending_show_focus=None,
        )

        MainFrame.show_and_focus(frame)

        frame.Show.assert_called_once_with()
        frame.Iconize.assert_called_once_with(False)
        self.assertIs(frame._pending_show_focus, category_tree)

    @patch("ui.main_frame.wx.CallAfter")
    def test_show_event_defers_pending_activation(self, call_after):
        target = Mock()
        activate_and_focus = Mock()
        event = Mock(IsShown=Mock(return_value=True))
        frame = SimpleNamespace(
            _pending_show_focus=target,
            _activate_and_focus=activate_and_focus,
        )

        MainFrame._on_show(frame, event)

        event.Skip.assert_called_once_with()
        self.assertIsNone(frame._pending_show_focus)
        call_after.assert_called_once_with(activate_and_focus, target)

    @patch("ui.main_frame.wx.CallAfter")
    def test_initial_show_event_without_pending_target_does_not_activate(
        self,
        call_after,
    ):
        event = Mock(IsShown=Mock(return_value=True))
        frame = SimpleNamespace(
            _pending_show_focus=None,
        )

        MainFrame._on_show(frame, event)

        event.Skip.assert_called_once_with()
        call_after.assert_not_called()

    @patch("ui.main_frame.wx.CallAfter")
    @patch("ui.main_frame.windows.activate_window", return_value=True)
    def test_deferred_activation_focuses_frame_before_scheduling_child(
        self,
        activate_window,
        call_after,
    ):
        target = Mock()
        focus_restored_control = Mock()
        frame = SimpleNamespace(
            IsShown=Mock(return_value=True),
            GetHandle=Mock(return_value=123),
            Raise=Mock(),
            SetFocus=Mock(),
            _focus_restored_control=focus_restored_control,
        )

        MainFrame._activate_and_focus(frame, target)

        activate_window.assert_called_once_with(123)
        frame.Raise.assert_called_once_with()
        frame.SetFocus.assert_called_once_with()
        target.SetFocus.assert_not_called()
        call_after.assert_called_once_with(focus_restored_control, target)

    def test_restored_child_is_focused_in_following_event_cycle(self):
        target = Mock()
        frame = SimpleNamespace(IsShown=Mock(return_value=True))

        MainFrame._focus_restored_control(frame, target)

        target.SetFocus.assert_called_once_with()

    def test_restored_child_is_not_focused_after_frame_was_hidden(self):
        target = Mock()
        frame = SimpleNamespace(IsShown=Mock(return_value=False))

        MainFrame._focus_restored_control(frame, target)

        target.SetFocus.assert_not_called()

    @patch("ui.main_frame.wx.CallLater")
    @patch("ui.main_frame.windows.activate_window", return_value=False)
    def test_failed_foreground_activation_is_retried_before_focusing(
        self,
        activate_window,
        call_later,
    ):
        target = Mock()
        retry = Mock()
        frame = SimpleNamespace(
            IsShown=Mock(return_value=True),
            GetHandle=Mock(return_value=123),
            Raise=Mock(),
            _activate_and_focus=retry,
        )

        MainFrame._activate_and_focus(frame, target)

        activate_window.assert_called_once_with(123)
        call_later.assert_called_once_with(50, retry, target, 4)
        frame.Raise.assert_not_called()
        target.SetFocus.assert_not_called()

    @patch("ui.main_frame.windows.activate_window")
    def test_pending_activation_stops_after_frame_is_hidden(self, activate_window):
        frame = SimpleNamespace(IsShown=Mock(return_value=False))

        MainFrame._activate_and_focus(frame, Mock())

        activate_window.assert_not_called()

    def test_layout_timer_delegates_to_binding(self):
        frame = SimpleNamespace(
            _global_hotkey=Mock(refresh_keyboard_layout=Mock(return_value=None)),
            _settings_controller=Mock(),
        )

        MainFrame._on_hotkey_layout_timer(frame, Mock())

        frame._global_hotkey.refresh_keyboard_layout.assert_called_once_with()
        (frame._settings_controller.show_hotkey_registration_error.assert_not_called())

    def test_layout_timer_reports_failed_registration(self):
        frame = SimpleNamespace(
            _global_hotkey=Mock(
                refresh_keyboard_layout=Mock(return_value=DEFAULT_TOGGLE_HOTKEY)
            ),
            _settings_controller=Mock(),
        )

        MainFrame._on_hotkey_layout_timer(frame, Mock())

        (
            frame._settings_controller.show_hotkey_registration_error.assert_called_once_with(
                DEFAULT_TOGGLE_HOTKEY
            )
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
