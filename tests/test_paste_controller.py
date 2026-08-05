import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.variables import (
    RenderedSnippet,
    UnknownVariableError,
    VariableRenderingCancelled,
)
from platform_support import clipboard_paste
from ui.paste_controller import PasteController


def render_unchanged(text, target_window=None):
    return RenderedSnippet(text)


class PasteControllerTestCase(unittest.TestCase):
    @patch("ui.paste_controller.windows.is_external_window")
    @patch("ui.paste_controller.windows.get_foreground_window")
    def test_initial_external_window_becomes_paste_target(
        self,
        get_foreground_window,
        is_external_window,
    ):
        get_foreground_window.return_value = 42
        is_external_window.return_value = True

        controller = PasteController(
            Mock(), Mock(), Mock(), Mock(), render_unchanged
        )

        self.assertEqual(controller._target_window, 42)
        self.assertEqual(controller.target_window, 42)

    @patch("ui.paste_controller.wx.CallLater")
    @patch("ui.paste_controller.windows.is_external_window")
    @patch("ui.paste_controller.windows.get_foreground_window")
    def test_insert_loads_snippet_hides_frame_and_delays_paste(
        self,
        get_foreground_window,
        is_external_window,
        call_later,
    ):
        get_foreground_window.return_value = 42
        is_external_window.return_value = True
        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(content="Example")
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
            "Example",
        )

    @patch("ui.paste_controller.wx.CallLater")
    @patch("ui.paste_controller.windows.is_external_window")
    @patch("ui.paste_controller.windows.get_foreground_window")
    def test_variable_text_is_resolved_before_the_window_is_hidden(
        self,
        get_foreground_window,
        is_external_window,
        call_later,
    ):
        get_foreground_window.return_value = 42
        is_external_window.return_value = True
        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(
            content="Today is {{date:long}}."
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

        render_snippet.assert_called_once_with("Today is {{date:long}}.", 42)
        before_paste.assert_called_once_with()
        call_later.assert_called_once_with(
            50,
            controller._paste_after_hide,
            "Today is 6. August 2026.",
        )

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
    ):
        get_foreground_window.return_value = 42
        is_external_window.return_value = True
        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(content="{{missing}}")
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
    ):
        model = Mock()
        model.get_snippet.return_value = SimpleNamespace(
            content="{{input:Customer number}}"
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
        controller = PasteController.__new__(PasteController)
        controller._target_window = 42
        controller.schedule_restore = Mock()

        controller._paste_after_hide("Example")

        paste_text.assert_called_once_with(42, "Example")
        controller.schedule_restore.assert_called_once_with(pending)

    @patch("ui.paste_controller.wx.MessageBox")
    @patch("ui.paste_controller.clipboard_paste.paste_text")
    def test_paste_failure_reveals_frame_and_reports_error(
        self,
        paste_text,
        message_box,
    ):
        paste_text.side_effect = clipboard_paste.PasteError("paste failed")
        controller = PasteController.__new__(PasteController)
        controller._target_window = 42
        controller._parent = Mock()
        controller._reveal_after_error = Mock()

        controller._paste_after_hide("Example")

        controller._reveal_after_error.assert_called_once_with()
        message_box.assert_called_once()

    @patch("ui.paste_controller.wx.CallLater")
    def test_transient_restore_failure_is_retried(self, call_later):
        pending = Mock()
        pending.restore_clipboard.side_effect = clipboard_paste.PasteError(
            "clipboard busy"
        )
        controller = PasteController.__new__(PasteController)

        controller._restore_clipboard(pending, 3)

        call_later.assert_called_once_with(
            100,
            controller._restore_clipboard,
            pending,
            2,
        )
        pending.discard_snapshot.assert_not_called()

    @patch("ui.paste_controller.wx.MessageBox")
    def test_final_restore_failure_discards_snapshot(self, message_box):
        pending = Mock()
        pending.restore_clipboard.side_effect = clipboard_paste.PasteError(
            "clipboard busy"
        )
        controller = PasteController.__new__(PasteController)
        controller._parent = Mock()

        controller._restore_clipboard(pending, 1)

        pending.discard_snapshot.assert_called_once_with()
        message_box.assert_called_once()


if __name__ == "__main__":
    unittest.main()
