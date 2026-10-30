import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.variables import (
    RenderedSnippet,
    UnknownVariableError,
    VariableRenderingCancelled,
)
from core.rich_text import ClipboardContent
from i18n import _
from platform_support import clipboard, clipboard_paste, windows
from ui.paste_controller import PasteController


def render_unchanged(text, target_window=None, markdown_enabled=False):
    return RenderedSnippet(text)


TARGET = windows.WindowIdentity(handle=42, thread_id=7, process_id=9)


def make_controller():
    """Create a controller without querying the native foreground window."""
    with patch.object(PasteController, "remember_foreground_window"):
        return PasteController(Mock(), Mock(), Mock(), Mock(), render_unchanged)


class TrayOverflowPasteRegressionTestCase(unittest.TestCase):
    def test_keyboard_tray_path_does_not_replace_notepad_with_shell_popups(self):
        from ui.main_frame import MainFrame
        from ui.tray_icon import TrayIcon

        classes = {
            42: "Notepad", 100: "Shell_TrayWnd",
            101: "TopLevelWindowForOverflowXamlIsland",
            102: "Xaml_WindowedPopupClass", 103: "#32768",
        }

        def get_class_name(handle, buffer, size):
            buffer.value = classes[handle]
            return len(buffer.value)

        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(content="Example", markdown_enabled=False)
        with (
            patch.object(windows, "get_foreground_window", return_value=42) as foreground,
            patch.object(windows, "is_external_window", return_value=True),
            patch.object(windows.user32, "GetClassNameW", side_effect=get_class_name),
            patch.object(windows.user32, "GetAncestor", side_effect=lambda h, flag: 101 if h in (102, 103) else h),
            patch.object(windows, "get_window_identity", side_effect=lambda h: windows.WindowIdentity(h, 7, 9)),
            patch.object(windows, "ForegroundWindowObserver"),
            patch("ui.paste_controller.wx.CallLater") as later,
        ):
            controller = PasteController(Mock(), model, Mock(), Mock(), render_unchanged)
            controller.start_tracking()
            frame = SimpleNamespace(
                _paste_controller=controller, _last_focused_control=None,
                category_tree=Mock(), Show=Mock(), Iconize=Mock(),
            )
            frame.show_and_focus = lambda: MainFrame.show_and_focus(frame)
            # Win+B -> hidden icons -> btText icon -> context menu. These
            # events used to leave a persistent shell popup as the paste target.
            for handle in (100, 101, 102, 103):
                controller.remember_window(handle)
            foreground.return_value = 102
            TrayIcon.on_restore(SimpleNamespace(_frame=frame), Mock())
            controller.insert_snippet(7)

        self.assertEqual(later.call_args.args[2], TARGET)


class PasteControllerTestCase(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(windows, "is_shell_window", return_value=False))

    @patch("ui.paste_controller.windows.ForegroundWindowObserver")
    @patch("ui.paste_controller.windows.get_foreground_window", return_value=None)
    def test_tracking_registers_once_and_can_be_stopped_repeatedly(self, foreground, observer_class):
        controller = PasteController(Mock(), Mock(), Mock(), Mock(), render_unchanged)

        controller.start_tracking()
        controller.start_tracking()
        controller.stop_tracking()
        controller.stop_tracking()

        observer_class.assert_called_once_with(controller.remember_window)
        self.assertEqual(observer_class.return_value.close.call_count, 2)

    @patch("ui.paste_controller.windows.ForegroundWindowObserver", side_effect=OSError("unavailable"))
    @patch("ui.paste_controller.windows.get_foreground_window", return_value=42)
    @patch("ui.paste_controller.windows.get_window_identity", return_value=TARGET)
    @patch("ui.paste_controller.windows.is_external_window", return_value=True)
    def test_failed_tracking_does_not_reuse_an_old_target_from_the_taskbar(
        self, external, identity, foreground, observer_class,
    ):
        controller = PasteController(Mock(), Mock(), Mock(), Mock(), render_unchanged)
        with self.assertLogs("bttext.paste", level="ERROR"):
            controller.start_tracking()
        self.assertIsNone(controller.target_window)

        # A directly observed application remains usable via the hotkey.
        controller.remember_foreground_window()
        self.assertEqual(controller.target_window, TARGET.handle)
        with patch.object(windows, "is_shell_window", return_value=True):
            controller.remember_foreground_window()
        self.assertIsNone(controller.target_window)

    @patch("ui.paste_controller.wx.CallLater")
    @patch("ui.paste_controller.windows.is_external_window")
    @patch("ui.paste_controller.windows.get_window_identity")
    @patch("ui.paste_controller.windows.get_foreground_window", return_value=42)
    @patch("ui.paste_controller.windows.ForegroundWindowObserver")
    def test_tray_restore_keeps_latest_app_across_taskbar_and_own_windows(
        self, observer_class, foreground, identity, external, call_later,
    ):
        from ui.main_frame import MainFrame
        from ui.tray_icon import TrayIcon

        second = windows.WindowIdentity(84, 8, 10)
        identity.side_effect = lambda handle: TARGET if handle == 42 else second
        external.side_effect = lambda handle: handle in (42, 84, 100, 101)
        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(
            content="Example", markdown_enabled=False,
        )
        controller = PasteController(Mock(), model, Mock(), Mock(), render_unchanged)
        controller.start_tracking()
        observe = observer_class.call_args.args[0]
        frame = SimpleNamespace(
            _paste_controller=controller, _last_focused_control=None,
            category_tree=Mock(), Show=Mock(), Iconize=Mock(),
        )
        frame.show_and_focus = lambda: MainFrame.show_and_focus(frame)

        # B becomes active while btText remains hidden; Windows then activates
        # the taskbar or its overflow popup before the tray command is handled.
        observe(84)
        with patch.object(windows, "is_shell_window", side_effect=lambda h: h in (100, 101)):
            for handle in (100, 101):
                observe(handle)
                foreground.return_value = handle
                TrayIcon.on_restore(SimpleNamespace(_frame=frame), Mock())
                self.assertEqual(controller.target_window, 84)
            observe(200)  # The restored btText window belongs to our process.
            controller.insert_snippet(7)

        self.assertEqual(call_later.call_args.args[2], second)

    @patch("ui.paste_controller.wx.CallLater")
    def test_foreground_changes_during_rendering_do_not_redirect_current_paste(self, call_later):
        second = windows.WindowIdentity(84, 8, 10)
        controller = make_controller()
        controller._target_window = TARGET
        controller._parent = Mock()
        controller._model = Mock()
        controller._model.get_snippet.return_value = SimpleNamespace(
            content="{{input:Name}}", markdown_enabled=False,
        )
        controller._before_paste = Mock()

        def render(text, target, markdown):
            self.assertEqual(target, TARGET.handle)
            controller._target_window = second
            return RenderedSnippet("Ada")

        controller._render_snippet = render
        controller.insert_snippet(7)

        self.assertEqual(call_later.call_args.args[2], TARGET)

    @patch("ui.paste_controller.windows.get_window_identity", return_value=TARGET)
    @patch("ui.paste_controller.windows.is_external_window")
    @patch("ui.paste_controller.windows.get_foreground_window")
    def test_initial_external_window_becomes_paste_target(
        self,
        get_foreground_window,
        is_external_window,
        get_window_identity,
    ):
        get_foreground_window.return_value = 42
        is_external_window.return_value = True

        controller = PasteController(
            Mock(), Mock(), Mock(), Mock(), render_unchanged
        )

        self.assertEqual(controller._target_window, TARGET)
        self.assertEqual(controller.target_window, 42)

    @patch("ui.paste_controller.windows.get_window_identity", return_value=TARGET)
    @patch("ui.paste_controller.wx.CallLater")
    @patch("ui.paste_controller.windows.is_external_window")
    @patch("ui.paste_controller.windows.get_foreground_window")
    def test_insert_loads_snippet_hides_frame_and_delays_paste(
        self,
        get_foreground_window,
        is_external_window,
        call_later,
        get_window_identity,
    ):
        get_foreground_window.return_value = 42
        is_external_window.return_value = True
        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(
            content="Example", markdown_enabled=False
        )
        before_paste = Mock()
        controller = PasteController(
            Mock(),
            model,
            before_paste,
            Mock(),
            render_unchanged,
        )

        controller.insert_snippet(7)

        model.get_snippet.assert_called_once_with(7)
        before_paste.assert_called_once_with()
        call_later.assert_called_once_with(
            50,
            controller._paste_after_hide,
            TARGET,
            ClipboardContent("Example"),
        )

    @patch("ui.paste_controller.windows.get_window_identity", return_value=TARGET)
    @patch("ui.paste_controller.wx.CallLater")
    @patch("ui.paste_controller.windows.is_external_window")
    @patch("ui.paste_controller.windows.get_foreground_window")
    def test_variable_text_is_resolved_before_the_window_is_hidden(
        self,
        get_foreground_window,
        is_external_window,
        call_later,
        get_window_identity,
    ):
        get_foreground_window.return_value = 42
        is_external_window.return_value = True
        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(
            content="Today is {{date:long}}.", markdown_enabled=False
        )
        before_paste = Mock()
        render_snippet = Mock(
            return_value=RenderedSnippet("Today is 6. August 2026.")
        )
        controller = PasteController(
            Mock(),
            model,
            before_paste,
            Mock(),
            render_snippet,
        )

        controller.insert_snippet(7)

        render_snippet.assert_called_once_with(
            "Today is {{date:long}}.",
            42,
            False,
        )
        before_paste.assert_called_once_with()
        call_later.assert_called_once_with(
            50,
            controller._paste_after_hide,
            TARGET,
            ClipboardContent("Today is 6. August 2026."),
        )

    @patch("ui.paste_controller.windows.get_window_identity", return_value=TARGET)
    @patch("ui.paste_controller.wx.CallLater")
    @patch("ui.paste_controller.windows.is_external_window", return_value=True)
    @patch("ui.paste_controller.windows.get_foreground_window", return_value=42)
    def test_cursor_offset_is_forwarded_to_delayed_paste(
        self,
        get_foreground_window,
        is_external_window,
        call_later,
        get_window_identity,
    ):
        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(
            content="A{{cursor}}BC", markdown_enabled=False
        )
        controller = PasteController(
            Mock(),
            model,
            Mock(),
            Mock(),
            Mock(return_value=RenderedSnippet("ABC", 2)),
        )

        controller.insert_snippet(7)

        call_later.assert_called_once_with(
            50,
            controller._paste_after_hide,
            TARGET,
            ClipboardContent("ABC", cursor_offset_from_end=2),
        )

    @patch("ui.paste_controller.windows.get_window_identity", return_value=TARGET)
    @patch("ui.paste_controller.show_variable_error")
    @patch("ui.paste_controller.wx.CallLater")
    @patch("ui.paste_controller.windows.is_external_window")
    @patch("ui.paste_controller.windows.get_foreground_window")
    def test_variable_error_does_not_hide_or_schedule_paste(
        self,
        get_foreground_window,
        is_external_window,
        call_later,
        show_error,
        get_window_identity,
    ):
        get_foreground_window.return_value = 42
        is_external_window.return_value = True
        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(
            content="{{missing}}",
            markdown_enabled=False,
        )
        before_paste = Mock()
        render_snippet = Mock(
            side_effect=UnknownVariableError(
                "variable_unknown",
                "Unknown variable {name}",
                name="missing",
                position=0,
            )
        )
        controller = PasteController(
            Mock(), model, before_paste, Mock(), render_snippet
        )

        controller.insert_snippet(7)

        before_paste.assert_not_called()
        call_later.assert_not_called()
        show_error.assert_called_once()

    @patch("ui.paste_controller.windows.get_window_identity", return_value=TARGET)
    @patch("ui.paste_controller.show_variable_error")
    @patch("ui.paste_controller.wx.CallLater")
    @patch("ui.paste_controller.windows.is_external_window", return_value=True)
    @patch("ui.paste_controller.windows.get_foreground_window", return_value=42)
    def test_cancelled_input_does_not_hide_or_report_an_error(
        self,
        get_foreground_window,
        is_external_window,
        call_later,
        show_error,
        get_window_identity,
    ):
        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(
            content="{{input:Customer number}}",
            markdown_enabled=False,
        )
        before_paste = Mock()
        controller = PasteController(
            Mock(),
            model,
            before_paste,
            Mock(),
            Mock(side_effect=VariableRenderingCancelled()),
        )

        controller.insert_snippet(7)

        before_paste.assert_not_called()
        call_later.assert_not_called()
        show_error.assert_not_called()

    @patch("ui.paste_controller.clipboard_paste.paste_text")
    def test_successful_paste_schedules_clipboard_restore(self, paste_text):
        pending = Mock()
        paste_text.return_value = pending
        controller = make_controller()
        controller.schedule_restore = Mock()
        controller._clipboard_session = clipboard_paste.ClipboardPasteSession()

        content = ClipboardContent("Example")
        controller._paste_after_hide(TARGET, content)

        paste_text.assert_called_once_with(
            TARGET, content, session=controller._clipboard_session
        )
        controller.schedule_restore.assert_called_once_with(pending)

    @patch("ui.paste_controller.keyboard_input.move_cursor_left")
    @patch("ui.paste_controller.clipboard_paste.paste_text")
    def test_successful_paste_moves_cursor_before_scheduling_restore(
        self,
        paste_text,
        move_cursor_left,
    ):
        pending = Mock()
        paste_text.return_value = pending
        controller = make_controller()
        controller.schedule_restore = Mock()
        controller._clipboard_session = clipboard_paste.ClipboardPasteSession()

        controller._paste_after_hide(
            TARGET,
            ClipboardContent("ABC", cursor_offset_from_end=2),
        )

        move_cursor_left.assert_called_once_with(2)
        controller.schedule_restore.assert_called_once_with(pending)

    @patch("ui.paste_controller.clipboard_paste.paste_text")
    def test_paste_failure_reveals_frame_and_reports_error(
        self,
        paste_text,
    ):
        paste_text.side_effect = clipboard.ClipboardError("paste failed")
        controller = make_controller()
        controller._parent = Mock()
        controller._reveal_after_error = Mock()
        controller._clipboard_session = clipboard_paste.ClipboardPasteSession()

        controller._paste_after_hide(TARGET, "Example")

        controller._reveal_after_error.assert_called_once_with(
            "paste failed",
            _("Paste error"),
        )

    @patch("ui.paste_controller.wx.CallLater")
    def test_transient_restore_failure_is_retried(self, call_later):
        pending = Mock()
        pending.restore_clipboard.side_effect = clipboard.ClipboardError(
            "clipboard busy"
        )
        controller = make_controller()

        controller._restore_clipboard(pending, 3)

        call_later.assert_called_once_with(
            100,
            controller._restore_clipboard,
            pending,
            2,
        )
        pending.discard_snapshot.assert_not_called()

    def test_final_restore_failure_discards_snapshot_and_reveals_error(self):
        pending = Mock()
        pending.restore_clipboard.side_effect = clipboard.ClipboardError(
            "clipboard busy"
        )
        controller = make_controller()
        controller._reveal_after_error = Mock()

        controller._restore_clipboard(pending, 1)

        pending.discard_snapshot.assert_called_once_with()
        controller._reveal_after_error.assert_called_once_with(
            _(
                "The previous clipboard contents could not be restored "
                "after multiple attempts. The clipboard may still contain "
                "the inserted snippet.\n\n{}"
            ).format("clipboard busy"),
            _("Clipboard restore error"),
        )


class PasteShutdownTestCase(unittest.TestCase):
    def setUp(self):
        self.controller = make_controller()
        self.now = 10.0
        self.enterContext(patch("ui.paste_controller.time.monotonic", side_effect=lambda: self.now))
        self.sleep = self.enterContext(patch("ui.paste_controller.time.sleep"))
        self.later = self.enterContext(patch("ui.paste_controller.wx.CallLater", side_effect=lambda *args: Mock()))

    def test_shutdown_stops_restore_timer_and_keeps_remaining_paste_grace(self):
        pending = Mock()
        self.controller.schedule_restore(pending)
        timer = self.controller._pending_restores[pending].timer
        self.now += 0.125

        self.controller.shutdown()
        self.controller.shutdown()

        timer.Stop.assert_called_once_with()
        self.sleep.assert_called_once_with(0.375)
        pending.restore_clipboard.assert_called_once_with()
        pending.discard_snapshot.assert_not_called()
        self.assertEqual(self.controller._pending_restores, {})
        self.controller._reveal_after_error.assert_not_called()

    def test_shutdown_retries_busy_clipboard_without_creating_more_timers(self):
        pending = Mock()
        pending.restore_clipboard.side_effect = [clipboard.ClipboardError("busy"), None]
        self.controller.schedule_restore(pending)
        self.now += 1

        self.controller.shutdown()

        self.assertEqual(pending.restore_clipboard.call_count, 2)
        self.sleep.assert_called_once_with(0.1)
        self.assertEqual(self.later.call_count, 1)
        pending.discard_snapshot.assert_not_called()

    def test_shutdown_logs_and_releases_snapshot_after_bounded_failures(self):
        pending = Mock()
        pending.restore_clipboard.side_effect = clipboard.ClipboardError("busy")
        self.controller.schedule_restore(pending)
        self.now += 1

        with self.assertLogs("bttext.paste", level="ERROR"):
            self.controller.shutdown()

        self.assertEqual(pending.restore_clipboard.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)
        pending.discard_snapshot.assert_called_once_with()
        self.controller._reveal_after_error.assert_not_called()

    def test_shutdown_takes_over_an_already_scheduled_retry(self):
        pending = Mock()
        pending.restore_clipboard.side_effect = [clipboard.ClipboardError("busy"), None]
        self.controller.schedule_restore(pending)
        self.now += 0.5
        self.controller._restore_clipboard(pending, 3)
        retry = self.controller._pending_restores[pending].timer
        self.now += 1

        self.controller.shutdown()
        # A callback already delivered to wx cannot run recovery a second time.
        self.controller._restore_clipboard(pending, 2)

        retry.Stop.assert_called_once_with()
        self.assertEqual(pending.restore_clipboard.call_count, 2)
        self.assertEqual(self.later.call_count, 2)

    def test_completed_restores_are_not_retained_until_shutdown(self):
        pending = Mock()
        self.controller.schedule_restore(pending)
        self.controller._restore_clipboard(pending, 3)

        self.controller.shutdown()

        pending.restore_clipboard.assert_called_once_with()
        self.sleep.assert_not_called()

    @patch("ui.paste_controller.clipboard_paste.paste_text")
    def test_shutdown_prevents_delayed_and_new_manual_pastes(self, paste):
        self.controller.shutdown()
        self.controller.insert_snippet(7)
        self.controller._paste_after_hide(TARGET, ClipboardContent("Example"))

        self.controller._model.get_snippet.assert_not_called()
        paste.assert_not_called()
        self.later.assert_not_called()

    def test_shutdown_during_variable_input_does_not_schedule_a_paste(self):
        self.controller._target_window = TARGET
        self.controller._model.get_snippet.return_value = SimpleNamespace(
            content="{{input:Name}}", markdown_enabled=False,
        )

        def render(*args):
            self.controller.shutdown()
            return RenderedSnippet("Ada")

        self.controller._render_snippet = render
        self.controller.insert_snippet(7)

        self.controller._before_paste.assert_not_called()
        self.later.assert_not_called()

    def test_paste_returning_after_shutdown_is_restored_without_a_timer(self):
        pending = Mock()
        self.controller.shutdown()

        self.controller.schedule_restore(pending)

        self.sleep.assert_called_once_with(0.5)
        pending.restore_clipboard.assert_called_once_with()
        self.later.assert_not_called()


if __name__ == "__main__":
    unittest.main()
