"""Keep the typed boundary character through expansion and variable prompts."""

import ctypes
import unittest
from unittest.mock import ANY, Mock, patch

import wx

from core.app_settings import AppSettings
from core.datamodel import Snippet
from core.events import EventEmitter
from core.variables import RenderedSnippet, UnknownVariableError, VariableRenderingCancelled
from platform_support import clipboard, hotstrings, keyboard_input, windows
from ui.hotstring_controller import HotstringController


TARGET = windows.WindowIdentity(42, 7, 9)
CONTEXT = (42, 43, 44)


class CapturedBoundaryTestCase(unittest.TestCase):
    def test_hook_captures_punctuation_but_keeps_native_control_keys(self):
        cases = (
            (0xBC, ";", True, False, ";"),
            (0xBE, ":", True, False, ":"),
            (0xDB, "?", True, False, "?"),
            (ord("Q"), "@", False, True, "@"),
            (hotstrings.VK_SPACE, " ", False, False, hotstrings.VK_SPACE),
            (hotstrings.VK_RETURN, "\r", False, False, hotstrings.VK_RETURN),
        )
        for key, character, shift, altgr, expected in cases:
            with self.subTest(character=character):
                matched = Mock(return_value=True)
                hook = hotstrings.KeyboardHook(matched)
                snippet = object()
                hook.update({"x": snippet})
                hook._matcher.character("x")
                hook._input_context = CONTEXT
                event = hotstrings.KBDLLHOOKSTRUCT(key, 0, 0, 0, 0)
                with (
                    patch.object(hook, "_get_input_context", return_value=CONTEXT),
                    patch.object(hook, "_translate", return_value=character),
                    patch.object(hook, "_is_key_down", return_value=shift),
                    patch.object(hook, "_is_altgr_down", return_value=altgr),
                    patch.object(hook, "_has_non_text_modifier_chord", return_value=False),
                    patch.object(hotstrings.user32, "CallNextHookEx", return_value=0),
                ):
                    result = hook._hook_callback(0, hotstrings.WM_KEYDOWN, ctypes.addressof(event))
                self.assertEqual(result, 1)
                matched.assert_called_once_with(snippet, expected, ANY)
                self.assertEqual(matched.call_args.args[2].context, CONTEXT)

    def test_tab_and_shift_tab_are_forwarded_and_clear_the_trigger(self):
        for shift in (False, True):
            with self.subTest(shift=shift):
                matched = Mock(return_value=True)
                hook = hotstrings.KeyboardHook(matched)
                hook.update({"x": object()})
                hook._matcher.character("x")
                hook._input_context = CONTEXT
                event = hotstrings.KBDLLHOOKSTRUCT(hotstrings.VK_TAB, 0, 0, 0, 0)
                with (
                    patch.object(hook, "_get_input_context", return_value=CONTEXT),
                    patch.object(hook, "_translate", return_value="\t") as translate,
                    patch.object(hook, "_is_key_down", return_value=shift),
                    patch.object(hook, "_is_altgr_down", return_value=False),
                    patch.object(hook, "_has_non_text_modifier_chord", return_value=False),
                    patch.object(hotstrings.user32, "CallNextHookEx", return_value=37) as forward,
                ):
                    for message in (hotstrings.WM_KEYDOWN, hotstrings.WM_KEYUP):
                        result = hook._hook_callback(0, message, ctypes.addressof(event))
                        self.assertEqual(result, 37)
                        forward.assert_called_with(None, 0, message, ctypes.addressof(event))
                matched.assert_not_called()
                translate.assert_not_called()
                self.assertIsNone(hook._matcher.character(" "))

    def test_queued_callback_retains_the_character(self):
        with (
            patch("ui.hotstring_controller.hotstrings.KeyboardHook"),
            patch("ui.hotstring_controller.windows.is_external_window", return_value=True),
            patch("ui.hotstring_controller.windows.get_window_identity", return_value=TARGET),
            patch("ui.hotstring_controller.wx.CallAfter") as queue,
        ):
            controller = HotstringController(Mock(), EventEmitter(), Mock(),
                lambda: AppSettings(), Mock(), Mock(), Mock())
            checkpoint = hotstrings.InputCheckpoint(CONTEXT)
            snippet = Snippet("Test", "Text", 1, hotstring="x")
            self.assertTrue(controller._queue_expansion(snippet, ";", checkpoint))
            callback, *arguments = queue.call_args.args
            with patch.object(controller, "_expand") as expand:
                callback(*arguments)
            expand.assert_called_once_with(TARGET, snippet, ";", checkpoint)


class BoundaryControllerTestCase(unittest.TestCase):
    def test_success_cancel_and_render_error_retain_original_character(self):
        for outcome in ("success", "cancel", "error"):
            for preserve in (False, True):
                with self.subTest(outcome=outcome, preserve=preserve):
                    renderer = Mock(return_value=RenderedSnippet("Expanded"))
                    if outcome == "cancel":
                        renderer.side_effect = VariableRenderingCancelled
                    elif outcome == "error":
                        renderer.side_effect = UnknownVariableError(
                            "variable_unknown", "Unknown variable", name="missing", position=0,
                        )
                    with (
                        patch("ui.hotstring_controller.hotstrings.KeyboardHook"),
                        patch("ui.hotstring_controller.show_variable_error") as show_error,
                        patch("platform_support.hotstring_expansion.windows.matches_window_identity", return_value=True),
                        patch("platform_support.hotstring_expansion.windows.activate_window_identity", return_value=True),
                        patch.object(keyboard_input, "send_boundary") as replay,
                        patch.object(keyboard_input, "send_hotstring_replacement") as replace,
                    ):
                        controller = HotstringController(Mock(), EventEmitter(), Mock(),
                            lambda: AppSettings(preserve_hotstring_boundary=preserve),
                            Mock(), Mock(), renderer, clipboard_session=Mock())
                        controller._expand(TARGET, Snippet("Test", "{{input:Name}}", 1, hotstring="x"),
                            ";", hotstrings.InputCheckpoint(CONTEXT))
                    if outcome == "success":
                        replace.assert_called_once_with(1, ";" if preserve else None)
                        replay.assert_not_called()
                    else:
                        # Cancellation/error must replay the suppressed original,
                        # even when successful expansions would discard it.
                        replay.assert_called_once_with(";")
                        replace.assert_not_called()
                    self.assertEqual(show_error.called, outcome == "error")


class BoundaryInputTestCase(unittest.TestCase):
    def setUp(self):
        state = patch.object(keyboard_input.user32, "GetAsyncKeyState", return_value=0)
        state.start()
        self.addCleanup(state.stop)

    def test_unicode_replay_is_balanced_tagged_and_independent_of_later_key_state(self):
        for character in (";", ":", "?", "@", "—", "🙂"):
            with self.subTest(character=character):
                captured = []
                def record(count, values, size):
                    self.assertEqual(size, ctypes.sizeof(keyboard_input.INPUT))
                    captured.extend((v.ki.wVk, v.ki.wScan, v.ki.dwFlags, v.ki.dwExtraInfo) for v in values)
                    return count
                with (
                    patch.object(keyboard_input.user32, "SendInput", side_effect=record) as send,
                    patch.object(hotstrings.user32, "GetAsyncKeyState", return_value=0),
                    patch.object(hotstrings.user32, "GetKeyboardLayout", side_effect=AssertionError("No retranslation")),
                ):
                    keyboard_input.send_boundary(character)
                encoded = character.encode("utf-16-le")
                units = [int.from_bytes(encoded[i:i + 2], "little") for i in range(0, len(encoded), 2)]
                self.assertEqual(captured, [
                    (0, unit, flags, keyboard_input.INPUT_MARKER)
                    for unit in units for flags in (4, 6)
                ])
                send.assert_called_once()

    def test_unicode_boundary_stays_in_the_atomic_replacement_batch(self):
        captured = []
        def record(count, values, size):
            captured.extend((v.ki.wVk, v.ki.wScan, v.ki.dwFlags) for v in values)
            return count
        with patch.object(keyboard_input.user32, "SendInput", side_effect=record) as send:
            keyboard_input.send_hotstring_replacement(1, ";")
        self.assertEqual(captured, [
            (8, 0, 0), (8, 0, 2),
            (0x11, 0, 0), (0x56, 0, 0), (0x56, 0, 2), (0x11, 0, 2),
            (0, ord(";"), 4), (0, ord(";"), 6),
        ])
        send.assert_called_once()

    def test_control_boundaries_still_send_native_key_actions(self):
        for key in (9, 13, 32):
            with self.subTest(key=key):
                captured = []
                def record(count, values, size):
                    captured.extend((v.ki.wVk, v.ki.wScan, v.ki.dwFlags) for v in values)
                    return count
                with patch.object(keyboard_input.user32, "SendInput", side_effect=record):
                    keyboard_input.send_boundary(key)
                self.assertEqual(captured, [(key, 0, 0), (key, 0, 2)])

    def test_partial_unicode_send_is_reported(self):
        for send in (lambda: keyboard_input.send_boundary(";"),
                     lambda: keyboard_input.send_hotstring_replacement(2, ";")):
            with patch.object(keyboard_input.user32, "SendInput", return_value=1):
                with self.assertRaises(clipboard.ClipboardError):
                    send()

    def test_invalid_text_boundary_sends_no_input(self):
        for text in ("", ";;"):
            for send in (lambda: keyboard_input.send_boundary(text),
                         lambda: keyboard_input.send_hotstring_replacement(2, text)):
                with patch.object(keyboard_input.user32, "SendInput") as native_send:
                    with self.assertRaises(ValueError):
                        send()
                    native_send.assert_not_called()


class NativeBoundaryInputTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def test_native_unicode_packets_insert_original_punctuation_after_a_modal_prompt(self):
        for character in (";", ":", "?", "@"):
            with self.subTest(character=character):
                target = wx.Dialog(None, title="Hotstring boundary regression")
                field = wx.TextCtrl(target)
                layout = wx.BoxSizer(wx.VERTICAL)
                layout.Add(field)
                target.SetSizerAndFit(layout)
                errors = []
                timers = []
                def finish():
                    try:
                        self.assertEqual(field.GetValue(), character)
                    except BaseException as error:
                        errors.append(error)
                    target.EndModal(wx.ID_OK)
                def replay_after_prompt():
                    try:
                        prompt = wx.Dialog(target, title="Variable prompt regression")
                        timer = wx.CallLater(20, prompt.EndModal, wx.ID_CANCEL)
                        try:
                            self.assertEqual(prompt.ShowModal(), wx.ID_CANCEL)
                        finally:
                            timer.Stop()
                            prompt.Destroy()
                        self.assertTrue(windows.activate_window(target.GetHandle()))
                        field.SetFocus()
                        windows.user32.SetFocus(field.GetHandle())
                        self.assertEqual(windows.get_foreground_window(), target.GetHandle())
                        keyboard_input.send_boundary(character)
                        timers.append(wx.CallLater(50, finish))
                    except BaseException as error:
                        errors.append(error)
                        target.EndModal(wx.ID_ABORT)
                timers.append(wx.CallLater(30, replay_after_prompt))
                timeout = wx.CallLater(3000, target.EndModal, wx.ID_ABORT)
                try:
                    result = target.ShowModal()
                    if errors:
                        raise errors[0]
                    self.assertEqual(result, wx.ID_OK)
                finally:
                    timeout.Stop()
                    for timer in timers:
                        timer.Stop()
                    target.Destroy()


if __name__ == "__main__":
    unittest.main()
