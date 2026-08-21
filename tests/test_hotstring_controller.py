import unittest
from unittest.mock import Mock, patch

from core import datamodel
from core.app_settings import AppSettings
from core.hotstrings import HotstringExpansionError
from core.variables import (
    RenderedSnippet,
    UnknownVariableError,
    VariableRenderingCancelled,
)
from ui.hotstring_controller import HotstringController


def render_unchanged(text, target_window=None):
    return RenderedSnippet(text)


class HotstringControllerTestCase(unittest.TestCase):
    def setUp(self):
        sound_patcher = patch("ui.hotstring_controller.sounds.play_sound")
        sound_patcher.start()
        self.addCleanup(sound_patcher.stop)

    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_snippet_mutations_refresh_hook_entries(self, keyboard_hook):
        ee = Mock()
        snippet = datamodel.Snippet(
            category_id=1,
            name="Greeting",
            content="Hello",
            hotstring="hello",
        )
        model = Mock()
        model.get_hotstring_snippets.return_value = [snippet]
        controller = HotstringController(
            Mock(),
            ee,
            model,
            lambda: AppSettings(),
            Mock(),
            Mock(),
            render_unchanged,
        )

        controller.refresh()

        keyboard_hook.return_value.update.assert_called_once_with({"hello": snippet})
        self.assertEqual(ee.on.call_count, 3)

    @patch("ui.hotstring_controller.wx.MessageBox")
    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_start_failure_is_reported(self, keyboard_hook, message_box):
        keyboard_hook.return_value.start.side_effect = OSError("hook unavailable")
        controller = HotstringController(
            Mock(),
            Mock(),
            Mock(),
            lambda: AppSettings(),
            Mock(),
            Mock(),
            render_unchanged,
        )

        self.assertFalse(controller.start())

        message_box.assert_called_once()

    @patch("ui.hotstring_controller.wx.CallAfter")
    @patch("ui.hotstring_controller.windows.is_external_window")
    @patch("ui.hotstring_controller.windows.get_foreground_window")
    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_match_from_external_window_is_queued_on_ui_thread(
        self,
        keyboard_hook,
        get_foreground_window,
        is_external_window,
        call_after,
    ):
        get_foreground_window.return_value = 42
        is_external_window.return_value = True
        controller = HotstringController(
            Mock(),
            Mock(),
            Mock(),
            lambda: AppSettings(),
            Mock(),
            Mock(),
            render_unchanged,
        )
        snippet = Mock()

        queued = controller._queue_expansion(snippet, 32)

        self.assertTrue(queued)
        call_after.assert_called_once_with(
            controller._expand,
            42,
            snippet,
            32,
        )

    @patch("ui.hotstring_controller.sounds.play_sound")
    @patch("ui.hotstring_controller.hotstring_expansion.expand_hotstring")
    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_expansion_restores_clipboard_and_notifies_when_enabled(
        self,
        keyboard_hook,
        expand_hotstring,
        play_sound,
    ):
        pending = Mock()
        expand_hotstring.return_value = pending
        schedule_restore = Mock()
        notify = Mock()
        settings = AppSettings(
            notify_hotstring_expansion=True,
            play_hotstring_sound=True,
        )
        controller = HotstringController(
            Mock(),
            Mock(),
            Mock(),
            lambda: settings,
            schedule_restore,
            notify,
            render_unchanged,
        )
        snippet = datamodel.Snippet(
            category_id=1,
            name="Greeting",
            content="Hello",
            hotstring="hello",
        )

        controller._expand(42, snippet, 32)

        expand_hotstring.assert_called_once_with(42, "Hello", 5, 32)
        schedule_restore.assert_called_once_with(pending)
        notify.assert_called_once_with(snippet)
        play_sound.assert_called_once_with("hotstring.wav")

    @patch("ui.hotstring_controller.sounds.play_sound")
    @patch("ui.hotstring_controller.hotstring_expansion.expand_hotstring")
    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_disabled_sound_is_not_played(
        self,
        keyboard_hook,
        expand_hotstring,
        play_sound,
    ):
        expand_hotstring.return_value = Mock()
        controller = HotstringController(
            Mock(),
            Mock(),
            Mock(),
            lambda: AppSettings(play_hotstring_sound=False),
            Mock(),
            Mock(),
            render_unchanged,
        )
        snippet = datamodel.Snippet(
            category_id=1,
            name="Greeting",
            content="Hello",
            hotstring="hello",
        )

        controller._expand(42, snippet, 32)

        play_sound.assert_not_called()

    @patch("ui.hotstring_controller.hotstring_expansion.expand_hotstring")
    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_variable_text_is_resolved_before_hotstring_expansion(
        self,
        keyboard_hook,
        expand_hotstring,
    ):
        pending = Mock()
        expand_hotstring.return_value = pending
        render_snippet = Mock(
            return_value=RenderedSnippet("Today is 6. August 2026.")
        )
        controller = HotstringController(
            Mock(),
            Mock(),
            Mock(),
            lambda: AppSettings(),
            Mock(),
            Mock(),
            render_snippet,
        )
        snippet = datamodel.Snippet(
            category_id=1,
            name="Dated greeting",
            content="Today is {{date:long}}.",
            hotstring="dated",
        )

        controller._expand(42, snippet, 32)

        render_snippet.assert_called_once_with("Today is {{date:long}}.", 42)
        expand_hotstring.assert_called_once_with(
            42,
            "Today is 6. August 2026.",
            5,
            32,
        )

    @patch("ui.hotstring_controller.keyboard_input.move_cursor_left")
    @patch("ui.hotstring_controller.hotstring_expansion.expand_hotstring")
    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_cursor_moves_across_suffix_and_preserved_boundary(
        self,
        keyboard_hook,
        expand_hotstring,
        move_cursor_left,
    ):
        expand_hotstring.return_value = Mock()
        controller = HotstringController(
            Mock(),
            Mock(),
            Mock(),
            lambda: AppSettings(preserve_hotstring_boundary=True),
            Mock(),
            Mock(),
            Mock(return_value=RenderedSnippet("ABC", 2)),
        )
        snippet = datamodel.Snippet(
            category_id=1,
            name="Cursor",
            content="A{{cursor}}BC",
            hotstring="cursor",
        )

        controller._expand(42, snippet, 32)

        move_cursor_left.assert_called_once_with(3)

    @patch("ui.hotstring_controller.show_variable_error")
    @patch("ui.hotstring_controller.hotstring_expansion.replay_suppressed_boundary")
    @patch("ui.hotstring_controller.hotstring_expansion.expand_hotstring")
    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_variable_error_does_not_expand_hotstring(
        self,
        keyboard_hook,
        expand_hotstring,
        replay_boundary,
        show_error,
    ):
        render_snippet = Mock(
            side_effect=UnknownVariableError(
                "variable_unknown",
                "Unknown variable {name}",
                name="missing",
                position=0,
            )
        )
        controller = HotstringController(
            Mock(),
            Mock(),
            Mock(),
            lambda: AppSettings(),
            Mock(),
            Mock(),
            render_snippet,
        )
        snippet = datamodel.Snippet(
            category_id=1,
            name="Broken",
            content="{{missing}}",
            hotstring="broken",
        )

        controller._expand(42, snippet, 32)

        expand_hotstring.assert_not_called()
        replay_boundary.assert_called_once_with(42, 32)
        show_error.assert_called_once()

    @patch("ui.hotstring_controller.show_variable_error")
    @patch("ui.hotstring_controller.hotstring_expansion.replay_suppressed_boundary")
    @patch("ui.hotstring_controller.hotstring_expansion.expand_hotstring")
    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_cancelled_input_restores_boundary_without_expanding(
        self,
        keyboard_hook,
        expand_hotstring,
        replay_boundary,
        show_error,
    ):
        controller = HotstringController(
            Mock(),
            Mock(),
            Mock(),
            lambda: AppSettings(),
            Mock(),
            Mock(),
            Mock(side_effect=VariableRenderingCancelled()),
        )
        snippet = datamodel.Snippet(
            category_id=1,
            name="Interactive",
            content="{{input:Customer number}}",
            hotstring="customer",
        )

        controller._expand(42, snippet, 32)

        expand_hotstring.assert_not_called()
        replay_boundary.assert_called_once_with(42, 32)
        show_error.assert_not_called()

    @patch("ui.hotstring_controller.wx.MessageBox")
    @patch("ui.hotstring_controller.format_user_error")
    @patch("ui.hotstring_controller.hotstring_expansion.replay_suppressed_boundary")
    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_cancelled_input_reports_boundary_replay_failure(
        self,
        keyboard_hook,
        replay_boundary,
        format_user_error,
        message_box,
    ):
        error = HotstringExpansionError(
            "hotstring_target_window_activation_failed",
            "The active window could not be activated.",
        )
        replay_boundary.side_effect = error
        format_user_error.return_value = (
            "Das aktive Fenster konnte nicht aktiviert werden."
        )
        controller = HotstringController(
            Mock(),
            Mock(),
            Mock(),
            lambda: AppSettings(),
            Mock(),
            Mock(),
            Mock(side_effect=VariableRenderingCancelled()),
        )
        snippet = datamodel.Snippet(
            category_id=1,
            name="Interactive",
            content="{{input:Customer number}}",
            hotstring="customer",
        )

        controller._expand(42, snippet, 32)

        replay_boundary.assert_called_once_with(42, 32)
        format_user_error.assert_called_once_with(error)
        message_box.assert_called_once()

    @patch("ui.hotstring_controller.wx.MessageBox")
    @patch("ui.hotstring_controller.format_user_error")
    @patch("ui.hotstring_controller.hotstring_expansion.expand_hotstring")
    @patch("ui.hotstring_controller.hotstrings.KeyboardHook")
    def test_structured_expansion_failure_is_localized_without_scheduling_restore(
        self,
        keyboard_hook,
        expand_hotstring,
        format_user_error,
        message_box,
    ):
        error = HotstringExpansionError(
            "hotstring_target_window_missing",
            "The active window no longer exists.",
        )
        expand_hotstring.side_effect = error
        format_user_error.return_value = (
            "Das aktive Fenster ist nicht mehr vorhanden."
        )
        schedule_restore = Mock()
        controller = HotstringController(
            Mock(),
            Mock(),
            Mock(),
            lambda: AppSettings(),
            schedule_restore,
            Mock(),
            render_unchanged,
        )
        snippet = datamodel.Snippet(
            category_id=1,
            name="Greeting",
            content="Hello",
            hotstring="hello",
        )

        controller._expand(42, snippet, 32)

        schedule_restore.assert_not_called()
        format_user_error.assert_called_once_with(error)
        message_box.assert_called_once()


if __name__ == "__main__":
    unittest.main()
