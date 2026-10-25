"""Regression coverage for queued hotstrings and their native input context."""

import ctypes
import os
import unittest
from unittest.mock import Mock, patch

import wx

from core.app_settings import AppSettings
from core.datamodel import Snippet
from core.events import EventEmitter
from core.variables import RenderedSnippet, VariableRenderingCancelled
from platform_support import hotstrings, keyboard_input, windows
from ui.hotstring_controller import HotstringController


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

    def test_focus_or_layout_change_is_permanent_invalidation(self):
        for changed in ((42, 99, 44), (42, 43, 99), (42, None, 44)):
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
            patch("platform_support.hotstring_expansion.keyboard_input.send_virtual_key") as send,
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

