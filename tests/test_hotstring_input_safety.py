"""Regression coverage for queued hotstrings and their native input context."""

import ctypes
import os
import unittest
from unittest.mock import Mock, patch

import wx

from core.app_settings import AppSettings
from core.builtin_variables import create_builtin_variable_engine
from core.datamodel import Snippet
from core.events import EventEmitter
from core.variables import RenderedSnippet, VariableRenderingCancelled
from platform_support import hotstrings, keyboard_input, windows
from ui.hotstring_controller import HotstringController
from ui.variable_resolver import SnippetVariableResolver


CONTEXT = (42, 43, 44)
TARGET = windows.WindowIdentity(42, 7, 9)


class CheckpointTestCase(unittest.TestCase):
    def setUp(self):
        self.hook = hotstrings.KeyboardHook(Mock())
        self.checkpoint = hotstrings.InputCheckpoint(CONTEXT)
        self.hook._pending_checkpoint = self.checkpoint

    def dispatch(self, message, key=ord("X"), flags=0, marker=0):
        event = hotstrings.KBDLLHOOKSTRUCT(key, 0, flags, 0, marker)
        with (
            patch.object(hotstrings.user32, "CallNextHookEx", return_value=37),
            patch.object(self.hook, "_get_input_context", return_value=CONTEXT),
            patch.object(self.hook, "_translate", return_value="x"),
            patch.object(self.hook, "_has_non_text_modifier_chord", return_value=False),
            patch.object(self.hook, "_is_key_down", return_value=False),
        ):
            return self.hook._hook_callback(hotstrings.HC_ACTION, message, ctypes.addressof(event))

    def test_new_external_keydowns_invalidate_pending_work(self):
        for key, flags in ((ord("X"), 0), (hotstrings.VK_LSHIFT, 0), (ord("X"), hotstrings.LLKHF_INJECTED)):
            with self.subTest(key=key, flags=flags):
                self.checkpoint.cancelled.clear()
                self.dispatch(hotstrings.WM_KEYDOWN, key, flags)
                self.assertTrue(self.checkpoint.cancelled.is_set())

    def test_key_release_and_owned_injection_keep_checkpoint(self):
        self.dispatch(hotstrings.WM_KEYUP)
        self.dispatch(hotstrings.WM_KEYDOWN, flags=hotstrings.LLKHF_INJECTED, marker=keyboard_input.INPUT_MARKER)
        self.assertFalse(self.checkpoint.cancelled.is_set())

    def test_input_helper_replays_do_not_erase_the_physical_trigger(self):
        for key in (ord("X"), hotstrings.VK_SHIFT, hotstrings.VK_LCONTROL):
            with self.subTest(key=key):
                self.hook._matcher.reset()
                self.hook._matcher.character("a")
                self.dispatch(
                    hotstrings.WM_KEYDOWN, key, hotstrings.LLKHF_INJECTED,
                )
                self.assertEqual(self.hook._matcher._buffer, "a")

    def test_injected_modifier_does_not_cancel_unchanged_expansion(self):
        self.dispatch(
            hotstrings.WM_KEYDOWN, hotstrings.VK_SHIFT, hotstrings.LLKHF_INJECTED,
        )
        self.assertFalse(self.checkpoint.cancelled.is_set())

    def test_complete_trigger_survives_interleaved_input_helper_events(self):
        matches = []
        hook = hotstrings.KeyboardHook(
            lambda snippet, key, checkpoint: matches.append(checkpoint) or True,
        )
        hook.update({"hello": object()})
        with (
            patch.object(hotstrings.user32, "CallNextHookEx", return_value=0),
            patch.object(hook, "_get_input_context", return_value=CONTEXT),
            patch.object(hook, "_translate", side_effect=list("hello ")),
            patch.object(hook, "_has_non_text_modifier_chord", return_value=False),
            patch.object(hook, "_is_key_down", return_value=False),
        ):
            for character in "hello ":
                event = hotstrings.KBDLLHOOKSTRUCT(ord(character.upper()), 0, 0, 0, 0)
                result = hook._hook_callback(
                    0, hotstrings.WM_KEYDOWN, ctypes.addressof(event),
                )
                helper = hotstrings.KBDLLHOOKSTRUCT(
                    hotstrings.VK_SHIFT, 0, hotstrings.LLKHF_INJECTED, 0, 0,
                )
                hook._hook_callback(0, hotstrings.WM_KEYDOWN, ctypes.addressof(helper))
                hook._hook_callback(0, hotstrings.WM_KEYUP, ctypes.addressof(helper))
        self.assertEqual(result, 1)
        self.assertEqual(len(matches), 1)
        self.assertFalse(matches[0].cancelled.is_set())

    def test_input_arriving_during_context_query_invalidates_result(self):
        def query(window):
            self.checkpoint.cancelled.set()
            return CONTEXT
        with (
            patch.object(self.hook, "_get_foreground_window", return_value=42),
            patch.object(self.hook, "_get_input_context", side_effect=query),
        ):
            self.assertFalse(self.hook.is_current(self.checkpoint))

    def test_mouse_observer_failure_rolls_back_keyboard_hook(self):
        with patch.object(self.hook, "_install_mouse_hook", side_effect=OSError("observer unavailable")):
            with self.assertRaises(OSError):
                self.hook.start()
        self.assertIsNone(self.hook._handle)
        self.assertIsNone(self.hook._mouse_handle)
        self.assertIsNone(self.hook._thread)

    def test_variable_dialog_keyboard_input_keeps_checkpoint(self):
        with patch.object(self.hook, "_should_monitor", return_value=False):
            self.dispatch(hotstrings.WM_KEYDOWN)
        self.assertFalse(self.checkpoint.cancelled.is_set())

    def test_interactive_session_preserves_target_across_keyboard_activity(self):
        for foreground in (100, 42, 200):
            with self.subTest(foreground=foreground):
                with (
                    self.hook.expansion(self.checkpoint),
                    patch.object(self.hook, "_get_foreground_window", return_value=foreground),
                ):
                    self.hook.begin_input(self.checkpoint)
                    self.dispatch(hotstrings.WM_KEYDOWN)
                    self.assertFalse(self.checkpoint.cancelled.is_set())
                self.assertFalse(self.checkpoint.interactive.is_set())

    def test_interactive_session_is_cleared_after_failure(self):
        with self.assertRaises(RuntimeError):
            with self.hook.expansion(self.checkpoint):
                self.hook.begin_input(self.checkpoint)
                raise RuntimeError("render failed")
        self.assertFalse(self.checkpoint.interactive.is_set())
        self.dispatch(hotstrings.WM_KEYDOWN)
        self.assertTrue(self.checkpoint.cancelled.is_set())

    def test_interactive_session_does_not_recognize_nested_hotstrings(self):
        self.hook.update({"lookup": object()})
        self.checkpoint.cancelled.clear()
        with (
            self.hook.expansion(self.checkpoint),
            patch.object(self.hook._matcher, "character") as match,
        ):
            self.hook.begin_input(self.checkpoint)
            for character in "lookup ":
                self.dispatch(hotstrings.WM_KEYDOWN, ord(character.upper()))
        match.assert_not_called()
        self.hook._on_match.assert_not_called()
        self.assertIs(self.hook._pending_checkpoint, self.checkpoint)
        self.assertFalse(self.checkpoint.cancelled.is_set())

    def test_foreground_changes_only_survive_for_interactive_sessions(self):
        for interactive in (False, True):
            with self.subTest(interactive=interactive):
                self.checkpoint.cancelled.clear()
                self.checkpoint.interactive.clear()
                if interactive:
                    self.hook.begin_input(self.checkpoint)
                self.hook._observed_foreground_window = 42
                with (
                    patch.object(self.hook, "_get_foreground_window", return_value=100),
                    patch.object(windows, "get_window_identity", return_value=windows.WindowIdentity(100, 1, os.getpid() + 1)),
                    patch.object(self.hook, "_install_native_hook", return_value=1),
                    patch.object(hotstrings.time, "monotonic", return_value=1),
                    patch.object(hotstrings.user32, "UnhookWindowsHookEx", return_value=True),
                ):
                    self.hook._monitor_hook()
                self.assertEqual(self.checkpoint.cancelled.is_set(), not interactive)

    def test_interactive_session_survives_mouse_activity(self):
        for handle in (100, 42, None):
            for message in (0x0201, 0x020A):
                with self.subTest(handle=handle, message=message):
                    event = hotstrings.MSLLHOOKSTRUCT()
                    with (
                        self.hook.expansion(self.checkpoint),
                        patch.object(hotstrings.user32, "WindowFromPoint", return_value=handle),
                        patch.object(windows, "get_window_identity", return_value=None),
                        patch.object(hotstrings.user32, "CallNextHookEx", return_value=37),
                    ):
                        self.hook.begin_input(self.checkpoint)
                        self.assertEqual(self.hook._mouse_callback(0, message, ctypes.addressof(event)), 37)
                    self.assertFalse(self.checkpoint.cancelled.is_set())

    def test_interactive_session_does_not_bypass_model_refresh_or_stop(self):
        for action in (lambda: self.hook.update({}), self.hook.stop):
            self.checkpoint.cancelled.clear()
            with self.hook.expansion(self.checkpoint):
                self.hook.begin_input(self.checkpoint)
                action()
            self.assertTrue(self.checkpoint.cancelled.is_set())

    def test_focus_or_layout_change_is_permanent_invalidation(self):
        for changed in ((42, 99, 44), (42, 43, 99)):
            with self.subTest(changed=changed):
                checkpoint = hotstrings.InputCheckpoint(CONTEXT)
                with (
                    patch.object(self.hook, "_get_foreground_window", return_value=42),
                    patch.object(self.hook, "_get_input_context", side_effect=[changed, CONTEXT]),
                ):
                    self.assertFalse(self.hook.is_current(checkpoint))
                    self.assertFalse(self.hook.is_current(checkpoint))

    def test_own_prompt_can_be_foreground_only_during_rendering(self):
        with (
            patch.object(self.hook, "_get_foreground_window", return_value=100),
            patch.object(windows, "get_window_identity", return_value=windows.WindowIdentity(100, 1, os.getpid())),
            patch.object(self.hook, "_get_input_context", return_value=CONTEXT),
        ):
            self.assertTrue(self.hook.is_current(self.checkpoint, allow_own_foreground=True))
            self.assertFalse(self.hook.is_current(self.checkpoint))

    def test_inactive_target_focus_is_rechecked_after_own_prompt(self):
        for inactive_focus in (None, 101):
            with self.subTest(inactive_focus=inactive_focus):
                checkpoint = hotstrings.InputCheckpoint(CONTEXT)
                with (
                    patch.object(self.hook, "_get_foreground_window", side_effect=[100, 42]),
                    patch.object(windows, "get_window_identity", return_value=windows.WindowIdentity(100, 1, os.getpid())),
                    patch.object(self.hook, "_get_input_context", side_effect=lambda window: (
                        (42, inactive_focus, 44) if foreground[0] == 100 else CONTEXT
                    )),
                ):
                    foreground = [100]
                    self.assertTrue(self.hook.is_current(checkpoint, allow_own_foreground=True))
                    foreground[0] = 42
                    self.assertTrue(self.hook.is_current(checkpoint, allow_own_foreground=True))

    def test_post_prompt_focus_can_return_after_target_activation(self):
        with (
            patch.object(self.hook, "_get_foreground_window", return_value=42),
            patch.object(self.hook, "_get_input_context", side_effect=[(42, None, 44), CONTEXT]),
            patch.object(hotstrings.time, "sleep") as sleep,
        ):
            self.assertTrue(self.hook.is_current(self.checkpoint, allow_own_foreground=True))
        sleep.assert_called_once()
        self.assertFalse(self.checkpoint.cancelled.is_set())

    def test_missing_focus_before_rendering_uses_input_observers_without_waiting(self):
        with (
            patch.object(self.hook, "_get_foreground_window", return_value=42),
            patch.object(self.hook, "_get_input_context", return_value=(42, None, 44)),
            patch.object(hotstrings.time, "sleep") as sleep,
        ):
            self.assertTrue(self.hook.is_current(self.checkpoint))
        sleep.assert_not_called()
        self.assertFalse(self.checkpoint.cancelled.is_set())

    def test_initially_unavailable_focus_does_not_block_or_delay_expansion(self):
        for focus in (None, 43):
            for allow_own_foreground in (False, True):
                with (
                    self.subTest(focus=focus, allow_own_foreground=allow_own_foreground),
                    patch.object(self.hook, "_get_foreground_window", return_value=42),
                    patch.object(self.hook, "_get_input_context", return_value=(42, focus, 44)),
                    patch.object(hotstrings.time, "sleep") as sleep,
                ):
                    checkpoint = hotstrings.InputCheckpoint((42, None, 44))
                    self.assertTrue(self.hook.is_current(checkpoint, allow_own_foreground=allow_own_foreground))
                    self.assertFalse(checkpoint.cancelled.is_set())
                    sleep.assert_not_called()

    def test_missing_focus_does_not_bypass_window_or_layout_checks(self):
        for foreground, context in ((100, (42, None, 44)), (42, (42, None, 99))):
            with (
                self.subTest(foreground=foreground, context=context),
                patch.object(self.hook, "_get_foreground_window", return_value=foreground),
                patch.object(self.hook, "_get_input_context", return_value=context),
                patch.object(windows, "get_window_identity", return_value=windows.WindowIdentity(100, 1, os.getpid() + 1)),
            ):
                checkpoint = hotstrings.InputCheckpoint((42, None, 44))
                self.assertFalse(self.hook.is_current(checkpoint, allow_own_foreground=True))
                self.assertTrue(checkpoint.cancelled.is_set())

    def test_input_observers_cancel_without_field_focus(self):
        for action in ("keyboard", "mouse"):
            with self.subTest(action=action):
                checkpoint = hotstrings.InputCheckpoint((42, None, 44))
                self.hook._pending_checkpoint = checkpoint
                if action == "keyboard":
                    self.dispatch(hotstrings.WM_KEYDOWN)
                else:
                    event = hotstrings.MSLLHOOKSTRUCT()
                    with (
                        patch.object(hotstrings.user32, "WindowFromPoint", return_value=42),
                        patch.object(windows, "get_window_identity", return_value=TARGET),
                        patch.object(hotstrings.user32, "CallNextHookEx", return_value=0),
                    ):
                        self.hook._mouse_callback(0, 0x0201, ctypes.addressof(event))
                self.assertTrue(checkpoint.cancelled.is_set())
                self.assertFalse(self.hook.is_current(checkpoint, allow_own_foreground=True))

    def test_post_prompt_focus_wait_is_bounded_and_falls_back_when_unavailable(self):
        elapsed = [0.0]

        def advance(seconds):
            elapsed[0] += seconds

        with (
            patch.object(self.hook, "_get_foreground_window", return_value=42),
            patch.object(self.hook, "_get_input_context", return_value=(42, None, 44)),
            patch.object(hotstrings.time, "monotonic", side_effect=lambda: elapsed[0]),
            patch.object(hotstrings.time, "sleep", side_effect=advance),
        ):
            self.assertTrue(self.hook.is_current(self.checkpoint, allow_own_foreground=True))
        self.assertGreaterEqual(elapsed[0], hotstrings.TARGET_FOCUS_RESTORE_TIMEOUT_SECONDS)
        self.assertLess(elapsed[0], hotstrings.TARGET_FOCUS_RESTORE_TIMEOUT_SECONDS + 0.02)
        self.assertFalse(self.checkpoint.cancelled.is_set())

    def test_external_input_during_focus_restoration_cancels(self):
        with (
            patch.object(self.hook, "_get_foreground_window", return_value=42),
            patch.object(self.hook, "_get_input_context", return_value=(42, None, 44)),
            patch.object(hotstrings.time, "sleep", side_effect=lambda seconds: self.dispatch(hotstrings.WM_KEYDOWN)),
        ):
            self.assertFalse(self.hook.is_current(self.checkpoint, allow_own_foreground=True))
        self.assertTrue(self.checkpoint.cancelled.is_set())

    def test_restored_focus_in_different_field_or_layout_is_rejected(self):
        for changed in ((42, 99, 44), (42, 43, 99)):
            with (
                self.subTest(changed=changed),
                patch.object(self.hook, "_get_foreground_window", return_value=42),
                patch.object(self.hook, "_get_input_context", side_effect=[(42, None, 44), changed]),
                patch.object(hotstrings.time, "sleep"),
            ):
                checkpoint = hotstrings.InputCheckpoint(CONTEXT)
                self.assertFalse(self.hook.is_current(checkpoint, allow_own_foreground=True))
                self.assertTrue(checkpoint.cancelled.is_set())

    def test_other_foreground_window_during_focus_restoration_is_rejected(self):
        with (
            patch.object(self.hook, "_get_foreground_window", side_effect=[42, 100]),
            patch.object(self.hook, "_get_input_context", return_value=(42, None, 44)),
            patch.object(windows, "get_window_identity", return_value=windows.WindowIdentity(100, 1, os.getpid() + 1)),
            patch.object(hotstrings.time, "sleep"),
        ):
            self.assertFalse(self.hook.is_current(self.checkpoint, allow_own_foreground=True))
        self.assertTrue(self.checkpoint.cancelled.is_set())

    def test_external_mouse_actions_invalidate_even_from_own_prompt(self):
        for process_id, cancelled in ((os.getpid(), False), (os.getpid() + 1, True)):
            with self.subTest(process_id=process_id):
                self.checkpoint.cancelled.clear()
                event = hotstrings.MSLLHOOKSTRUCT()
                with (
                    patch.object(hotstrings.user32, "WindowFromPoint", return_value=100),
                    patch.object(
                        windows, "get_window_identity",
                        return_value=windows.WindowIdentity(100, 1, process_id),
                    ),
                    patch.object(hotstrings.user32, "CallNextHookEx", return_value=37),
                ):
                    result = self.hook._mouse_callback(0, 0x0201, ctypes.addressof(event))
                self.assertEqual(result, 37)
                self.assertEqual(self.checkpoint.cancelled.is_set(), cancelled)

    def test_model_refresh_and_stop_invalidate_queued_work(self):
        for action in (lambda: self.hook.update({}), self.hook.stop):
            self.checkpoint.cancelled.clear()
            action()
            self.assertTrue(self.checkpoint.cancelled.is_set())


class QueuedControllerTestCase(unittest.TestCase):
    def controller(self, renderer=None):
        with patch("ui.hotstring_controller.hotstrings.KeyboardHook"):
            controller = HotstringController(
                Mock(), EventEmitter(), Mock(), lambda: AppSettings(), Mock(), Mock(),
                renderer or Mock(return_value=RenderedSnippet("Expanded")),
            )
        return controller

    def test_stale_queue_does_not_render_or_replace_text(self):
        renderer = Mock()
        controller = self.controller(renderer)
        controller._hook.is_current.return_value = False
        with patch("ui.hotstring_controller.hotstring_expansion.expand_hotstring") as expand:
            controller._expand(
                TARGET, Snippet("Name", "Text", 1, hotstring=";sig"),
                32, hotstrings.InputCheckpoint(CONTEXT),
            )
        renderer.assert_not_called()
        expand.assert_not_called()

    def test_queue_accepts_target_with_unavailable_field_focus(self):
        controller = self.controller()
        checkpoint = hotstrings.InputCheckpoint((42, None, 44))
        snippet = Snippet("Name", "Text", 1, hotstring=";sig")
        with (
            patch.object(windows, "is_external_window", return_value=True),
            patch.object(windows, "get_window_identity", return_value=TARGET),
            patch("ui.hotstring_controller.wx.CallAfter") as queue,
            patch.object(controller, "_expand") as expand,
        ):
            self.assertTrue(controller._queue_expansion(snippet, 32, checkpoint))
            callback, *arguments = queue.call_args.args
            callback(*arguments)
        expand.assert_called_once_with(TARGET, snippet, 32, checkpoint)

    def test_successful_render_does_not_authorize_later_stale_input(self):
        controller = self.controller()
        controller._hook.is_current.side_effect = [True, False]
        with (
            patch("platform_support.hotstring_expansion.PendingPaste.prepare") as prepare,
            patch.object(keyboard_input, "send_hotstring_replacement") as replace,
        ):
            controller._expand(
                TARGET, Snippet("Name", "Text", 1, hotstring=";sig"),
                32, hotstrings.InputCheckpoint(CONTEXT),
            )
        prepare.assert_not_called()
        replace.assert_not_called()

    def test_queue_reservation_is_released_after_render_failure(self):
        controller = self.controller(Mock(side_effect=RuntimeError("render failed")))
        controller._queue_lock.acquire()
        with self.assertRaises(RuntimeError):
            controller._run_queued_expansion(
                TARGET, Snippet("Name", "Text", 1),
                32, hotstrings.InputCheckpoint(CONTEXT),
            )
        self.assertTrue(controller._queue_lock.acquire(blocking=False))
        controller._queue_lock.release()

    def test_input_during_cancelled_prompt_does_not_replay_boundary(self):
        controller = self.controller(Mock(side_effect=VariableRenderingCancelled))
        controller._hook.is_current.side_effect = [True, False]
        with (
            patch("platform_support.hotstring_expansion.windows.activate_window_identity") as activate,
            patch("platform_support.hotstring_expansion.keyboard_input.send_boundary") as send,
        ):
            controller._expand(
                TARGET, Snippet("Name", "Text", 1, hotstring=";sig"),
                32, hotstrings.InputCheckpoint(CONTEXT),
            )
        activate.assert_not_called()
        send.assert_not_called()

    def test_busy_expansion_leaves_new_boundary_native_and_releases_gate(self):
        controller = self.controller()
        checkpoint = hotstrings.InputCheckpoint(CONTEXT)
        with (
            patch("ui.hotstring_controller.windows.is_external_window", return_value=True),
            patch("ui.hotstring_controller.windows.get_window_identity", return_value=TARGET),
            patch("ui.hotstring_controller.wx.CallAfter") as queue,
        ):
            self.assertTrue(controller._queue_expansion(Mock(), 32, checkpoint))
            self.assertFalse(controller._queue_expansion(Mock(), 32, checkpoint))
            controller._hook.is_current.return_value = False
            callback, *arguments = queue.call_args.args
            callback(*arguments)
            self.assertTrue(controller._queue_expansion(Mock(), 32, checkpoint))


class InteractiveCheckpointTestCase(unittest.TestCase):
    def test_confirmed_prompt_rejects_missing_reused_or_inactive_target(self):
        for outcome in ("closed", "reused", "activation_failed", "foreground_stolen"):
            with self.subTest(outcome=outcome):
                foreground = [42]
                checkpoint = hotstrings.InputCheckpoint(CONTEXT)
                session = Mock()

                def request_inputs(labels):
                    foreground[0] = 500
                    return {"Name": "Ada"}

                def identity(handle):
                    if outcome == "closed":
                        return None
                    if outcome == "reused":
                        return windows.WindowIdentity(42, 8, 10)
                    return TARGET

                resolver = SnippetVariableResolver(
                    create_builtin_variable_engine(), request_inputs=request_inputs,
                )
                controller = HotstringController(
                    Mock(), EventEmitter(), Mock(), lambda: AppSettings(),
                    Mock(), Mock(), resolver.render, clipboard_session=session,
                )
                controller._hook._pending_checkpoint = checkpoint
                with (
                    patch.object(controller._hook, "_get_foreground_window", side_effect=lambda: foreground[0]),
                    patch.object(controller._hook, "_get_input_context", return_value=CONTEXT),
                    patch.object(windows, "get_window_identity", side_effect=identity),
                    patch.object(windows, "activate_window_identity", return_value=outcome == "foreground_stolen") as activate,
                    patch.object(keyboard_input, "send_hotstring_replacement") as replace,
                    patch.object(controller, "_show_hotstring_error") as show_error,
                ):
                    controller._expand(
                        TARGET, Snippet("Greeting", "Hello {{input:Name}}", 1, hotstring=";hi"),
                        32, checkpoint,
                    )
                self.assertFalse(checkpoint.interactive.is_set())
                replace.assert_not_called()
                if outcome in ("closed", "reused"):
                    session.prepare.assert_not_called()
                    activate.assert_not_called()
                    self.assertEqual(show_error.call_args.args[0].code, "hotstring_target_window_missing")
                else:
                    session.prepare.return_value.restore_clipboard.assert_called_once_with()
                    if outcome == "activation_failed":
                        self.assertEqual(show_error.call_args.args[0].code, "hotstring_target_window_activation_failed")
                    else:
                        show_error.assert_not_called()

    def test_confirmed_input_restores_target_after_minutes_and_new_foreground_windows(self):
        foreground = [42]
        elapsed = [0.0]
        context = [CONTEXT]
        session = Mock()
        restored = Mock()
        checkpoint = hotstrings.InputCheckpoint(CONTEXT)

        def request_inputs(labels):
            self.assertEqual(labels, ("Name",))
            for window in (100, 200, 300, 42, 400, 100):
                foreground[0] = window
                elapsed[0] += 120
                context[0] = (42, None, 99)
                hook._monitor_hook()
                event = hotstrings.KBDLLHOOKSTRUCT(ord("A"), 0, 0, 0, 0)
                hook._hook_callback(0, hotstrings.WM_KEYDOWN, ctypes.addressof(event))
                mouse = hotstrings.MSLLHOOKSTRUCT()
                hook._mouse_callback(0, 0x0201, ctypes.addressof(mouse))
            # Destroying the modal dialog may foreground another application's
            # newly opened window rather than btText or the original target.
            foreground[0] = 500
            return {"Name": "Ada"}

        def activate(target, **kwargs):
            self.assertEqual(target, TARGET)
            foreground[0] = 42
            context[0] = (42, 99, 99)
            return True

        resolver = SnippetVariableResolver(
            create_builtin_variable_engine(), request_inputs=request_inputs,
        )
        controller = HotstringController(
            Mock(), EventEmitter(), Mock(), lambda: AppSettings(), restored,
            Mock(), resolver.render, clipboard_session=session,
        )
        hook = controller._hook
        hook._pending_checkpoint = checkpoint
        hook._mouse_handle = 123
        with (
            patch.object(hook, "_get_foreground_window", side_effect=lambda: foreground[0]),
            patch.object(hook, "_get_input_context", side_effect=lambda *args: context[0]),
            patch.object(hook, "_should_monitor", side_effect=lambda: foreground[0] != 100),
            patch.object(hotstrings.time, "monotonic", side_effect=lambda: elapsed[0]),
            patch.object(hook, "_install_native_hook", return_value=1),
            patch.object(hook, "_install_mouse_hook", return_value=2),
            patch.object(hook, "_is_user_input_idle", return_value=True),
            patch.object(hotstrings.user32, "UnhookWindowsHookEx", return_value=True),
            patch.object(hotstrings.user32, "WindowFromPoint", side_effect=lambda point: foreground[0]),
            patch.object(windows, "get_window_identity", side_effect=lambda handle: windows.WindowIdentity(handle, 1, os.getpid() if handle == 100 else os.getpid() + 1)),
            patch.object(windows, "matches_window_identity", return_value=True),
            patch.object(windows, "activate_window_identity", side_effect=activate) as activation,
            patch.object(hotstrings.user32, "CallNextHookEx", return_value=0),
            patch.object(keyboard_input, "send_hotstring_replacement") as replace,
        ):
            controller._expand(
                TARGET, Snippet("Greeting", "Hello {{input:Name}}", 1, hotstring=";hi"),
                32, checkpoint,
            )
        activation.assert_called_once_with(TARGET, focus_window=43)
        replace.assert_called_once_with(3, 32)
        self.assertEqual(session.prepare.call_args.args[0].plain_text, "Hello Ada")
        restored.assert_called_once_with(session.prepare.return_value)

    def test_input_answers_survive_inactive_focus_but_reactivation_checks_target(self):
        cases = (
            (43, "success"), (43, "cancel"), (43, "changed_focus"), (43, "external_input"),
            (None, "success"), (None, "cancel"), (None, "external_input"),
            (43, "lookup_success"), (43, "lookup_cancel"),
            (None, "lookup_success"), (None, "lookup_cancel"),
        )
        for initial_focus, outcome in cases:
            with self.subTest(initial_focus=initial_focus, outcome=outcome):
                foreground = [42]
                initial_context = (42, initial_focus, 44)
                context = [initial_context]
                checkpoint = hotstrings.InputCheckpoint(initial_context)
                session = Mock()
                schedule_restore = Mock()
                controller = None

                def request_inputs(labels):
                    self.assertEqual(labels, ("Name",))
                    foreground[0] = 100
                    # An inactive application's GUI thread may have no focus.
                    context[0] = (42, None, 44)
                    event = hotstrings.KBDLLHOOKSTRUCT(ord("A"), 0, 0, 0, 0)
                    controller._hook._hook_callback(
                        0, hotstrings.WM_KEYDOWN, ctypes.addressof(event),
                    )
                    if outcome.startswith("lookup_"):
                        foreground[0] = 200
                        mouse = hotstrings.MSLLHOOKSTRUCT()
                        controller._hook._mouse_callback(0, 0x0201, ctypes.addressof(mouse))
                        controller._hook._monitor_hook()
                        controller._hook._hook_callback(
                            0, hotstrings.WM_KEYDOWN, ctypes.addressof(event),
                        )
                        self.assertFalse(checkpoint.cancelled.is_set())
                        foreground[0] = 100
                    if outcome == "external_input":
                        checkpoint.cancelled.set()
                    return None if outcome in ("cancel", "lookup_cancel") else {"Name": "Ada"}

                def activate(target, **kwargs):
                    self.assertEqual(target, TARGET)
                    foreground[0] = 42
                    context[0] = (42, 99, 44) if outcome == "changed_focus" else initial_context
                    return True

                resolver = SnippetVariableResolver(
                    create_builtin_variable_engine(), request_inputs=request_inputs,
                )
                controller = HotstringController(
                    Mock(), EventEmitter(), Mock(), lambda: AppSettings(),
                    schedule_restore, Mock(), resolver.render, clipboard_session=session,
                )
                hook = controller._hook
                hook._pending_checkpoint = checkpoint
                with (
                    patch.object(hook, "_get_foreground_window", side_effect=lambda: foreground[0]),
                    patch.object(hook, "_get_input_context", side_effect=lambda *args: context[0]),
                    patch.object(hook, "_should_monitor", side_effect=lambda: foreground[0] != 100),
                    patch.object(windows, "get_window_identity", side_effect=lambda handle: windows.WindowIdentity(handle, 1, os.getpid() if handle == 100 else os.getpid() + 1)),
                    patch.object(hotstrings.user32, "WindowFromPoint", return_value=200),
                    patch.object(hook, "_install_native_hook", return_value=1),
                    patch.object(hotstrings.user32, "UnhookWindowsHookEx", return_value=True),
                    patch.object(windows, "matches_window_identity", return_value=True),
                    patch.object(windows, "activate_window_identity", side_effect=activate),
                    patch.object(hotstrings.user32, "CallNextHookEx", return_value=0),
                    patch.object(keyboard_input, "send_hotstring_replacement") as replace,
                    patch.object(keyboard_input, "send_boundary") as replay,
                ):
                    controller._expand(
                        TARGET, Snippet("Greeting", "Hello {{input:Name}}", 1, hotstring=";hi"),
                        32, checkpoint,
                    )
                self.assertFalse(checkpoint.interactive.is_set())
                if outcome in ("success", "lookup_success", "changed_focus"):
                    self.assertEqual(session.prepare.call_args.args[0].plain_text, "Hello Ada")
                    replace.assert_called_once_with(3, 32)
                    schedule_restore.assert_called_once_with(session.prepare.return_value)
                else:
                    replace.assert_not_called()
                    schedule_restore.assert_not_called()
                if outcome in ("cancel", "lookup_cancel"):
                    replay.assert_called_once_with(32)
                    session.prepare.assert_not_called()
                else:
                    replay.assert_not_called()
                if outcome == "external_input":
                    session.prepare.assert_not_called()


class NativeQueuedInputTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def test_real_modal_queue_preserves_later_text_and_changed_field(self):
        for change in ("unchanged", "typing", "focus"):
            with self.subTest(change=change):
                dialog = wx.Dialog(None, title="Hotstring input regression")
                first = wx.TextCtrl(dialog, value=";sig")
                second = wx.TextCtrl(dialog, value="OTHER")
                sizer = wx.BoxSizer(wx.VERTICAL)
                sizer.Add(first)
                sizer.Add(second)
                dialog.SetSizerAndFit(sizer)
                errors = []
                snippet = Snippet("Signature", "Expanded", 1, hotstring=";sig")
                controller = HotstringController(
                    dialog, EventEmitter(), Mock(), lambda: AppSettings(),
                    Mock(), Mock(), Mock(return_value=RenderedSnippet("Expanded")),
                    clipboard_session=Mock(),
                )
                hook = controller._hook

                def finish():
                    dialog.EndModal(wx.ID_OK)

                def begin():
                    try:
                        windows.activate_window(dialog.GetHandle())
                        first.SetFocus()
                        windows.user32.SetFocus(first.GetHandle())
                        first.SetInsertionPointEnd()
                        checkpoint = hotstrings.InputCheckpoint(
                            hook._get_input_context(dialog.GetHandle()),
                        )
                        self.assertEqual(checkpoint.context[1], first.GetHandle())
                        hook._pending_checkpoint = checkpoint
                        self.assertTrue(controller._queue_expansion(snippet, 32, checkpoint))
                        if change == "typing":
                            first.WriteText("X")
                            event = hotstrings.KBDLLHOOKSTRUCT(ord("X"), 0, 0, 0, 0)
                            hook._hook_callback(0, hotstrings.WM_KEYDOWN, ctypes.addressof(event))
                        elif change == "focus":
                            second.SetFocus()
                            windows.user32.SetFocus(second.GetHandle())
                            second.SetInsertionPointEnd()
                            self.assertEqual(
                                hook._get_input_context(dialog.GetHandle())[1],
                                second.GetHandle(),
                            )
                        wx.CallAfter(finish)
                    except BaseException as error:
                        errors.append(error)
                        finish()

                with (
                    patch.object(hook, "_should_monitor", return_value=True),
                    patch("ui.hotstring_controller.windows.is_external_window", return_value=True),
                    patch.object(hook, "_translate", return_value="X"),
                    patch.object(hook, "_is_key_down", return_value=False),
                    patch.object(hook, "_has_non_text_modifier_chord", return_value=False),
                    patch.object(hotstrings.user32, "CallNextHookEx", return_value=0),
                    patch.object(keyboard_input, "send_hotstring_replacement") as replace,
                ):
                    timer = wx.CallLater(50, begin)
                    timeout = wx.CallLater(3000, dialog.EndModal, wx.ID_ABORT)
                    try:
                        self.assertEqual(dialog.ShowModal(), wx.ID_OK)
                        if errors:
                            raise errors[0]
                        self.assertEqual(first.GetValue(), ";sigX" if change == "typing" else ";sig")
                        self.assertEqual(second.GetValue(), "OTHER")
                        if change == "unchanged":
                            replace.assert_called_once_with(4, 32)
                        else:
                            replace.assert_not_called()
                            controller._clipboard_session.prepare.assert_not_called()
                    finally:
                        timer.Stop()
                        timeout.Stop()
                        dialog.Destroy()

