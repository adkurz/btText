"""Explicit paste/input chords must not inherit physically held modifiers."""

import ctypes
import time
import unittest
from unittest.mock import patch

import wx

from platform_support import clipboard, hotstring_expansion, keyboard_input, windows
from platform_support.clipboard_paste import ClipboardPasteSession


MODIFIERS = (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5)


class KeyboardModifierTestCase(unittest.TestCase):
    def test_altgr_is_released_before_control_and_restored_after_it(self):
        batches = []
        def record(count, values, size):
            batches.append([(item.ki.wVk, item.ki.dwFlags) for item in values])
            return count
        with (
            patch.object(keyboard_input.user32, "GetAsyncKeyState", side_effect=lambda key: 0x8000 if key in (0xA2, 0xA5) else 0),
            patch.object(keyboard_input.user32, "SendInput", side_effect=record),
        ):
            keyboard_input.send_hotstring_replacement(6, "?")
        self.assertEqual(batches[0][:2], [(0xA5, 3), (0xA2, 2)])
        self.assertEqual(batches[0][-2:], [(0xA2, 0), (0xA5, 1)])

    def test_held_modifiers_are_released_for_input_and_restored_afterwards(self):
        for held in ((0xA0,), (0xA1,), (0xA2, 0xA5), MODIFIERS):
            for operation in ("paste", "replace", "boundary", "cursor"):
                with self.subTest(held=held, operation=operation):
                    state = set(held)
                    body_states = []
                    def record(count, values, size):
                        for value in values:
                            key = value.ki.wVk
                            released = bool(value.ki.dwFlags & keyboard_input.KEYEVENTF_KEYUP)
                            if key in MODIFIERS or key == keyboard_input.VK_CONTROL:
                                if released:
                                    state.discard(key)
                                else:
                                    state.add(key)
                            elif not released:
                                body_states.append((key, set(state)))
                            self.assertEqual(value.ki.dwExtraInfo, keyboard_input.INPUT_MARKER)
                        return count
                    with (
                        patch.object(keyboard_input.user32, "GetAsyncKeyState", side_effect=lambda key: 0x8000 if key in state else 0),
                        patch.object(keyboard_input.user32, "SendInput", side_effect=record) as send,
                    ):
                        if operation == "paste":
                            keyboard_input.send_ctrl_v()
                        elif operation == "replace":
                            keyboard_input.send_hotstring_replacement(6, "?")
                        elif operation == "boundary":
                            keyboard_input.send_boundary("?")
                        else:
                            keyboard_input.move_cursor_left(2)
                    self.assertTrue(body_states)
                    for key, modifiers in body_states:
                        self.assertEqual(modifiers, {keyboard_input.VK_CONTROL} if key == keyboard_input.VK_V else set())
                    self.assertEqual(state, set(held))
                    send.assert_called_once()

    def test_partial_send_releases_synthetic_keys_and_restores_held_shift(self):
        state = {0xA1}
        calls = []
        def record(count, values, size):
            records = [(item.ki.wVk, item.ki.dwFlags) for item in values]
            calls.append(records)
            if len(calls) == 1:
                accepted = next(index + 1 for index, (key, flags) in enumerate(records)
                    if key == keyboard_input.VK_CONTROL and flags == 0)
            else:
                accepted = count
            for key, flags in records[:accepted]:
                if flags & keyboard_input.KEYEVENTF_KEYUP:
                    state.discard(key)
                else:
                    state.add(key)
            return accepted
        with (
            patch.object(keyboard_input.user32, "GetAsyncKeyState", side_effect=lambda key: 0x8000 if key in state else 0),
            patch.object(keyboard_input.user32, "SendInput", side_effect=record),
        ):
            with self.assertRaises(clipboard.ClipboardError):
                keyboard_input.send_hotstring_replacement(6, "?")
        self.assertEqual(len(calls), 2)
        self.assertEqual(state, {0xA1})


class NativePasteModifierTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def test_question_mark_pastes_with_left_and_right_shift_still_held(self):
        if any(keyboard_input.user32.GetAsyncKeyState(key) & 0x8000 for key in MODIFIERS + (0x5B, 0x5C)):
            self.skipTest("Native modifier test requires no physical modifier keys held")
        for rich in (False, True):
            for shift in (0xA0, 0xA1):
                with self.subTest(rich=rich, shift=shift):
                    target = wx.Dialog(None, title="Held-Shift hotstring paste regression")
                    field = wx.TextCtrl(target, value="__test",
                        style=wx.TE_MULTILINE | (wx.TE_RICH2 if rich else 0))
                    layout = wx.BoxSizer(wx.VERTICAL)
                    layout.Add(field)
                    target.SetSizerAndFit(layout)
                    pending = []
                    errors = []
                    chords = []
                    timers = []
                    shift_sent = []
                    def inject_shift(flags):
                        values = (keyboard_input.INPUT * 1)(keyboard_input._keyboard_input(shift, flags))
                        self.assertEqual(keyboard_input.user32.SendInput(
                            1, values, ctypes.sizeof(keyboard_input.INPUT)), 1)
                    def observe(event):
                        # Keep ambient typing out of this owned fixture. All
                        # keys relevant to deletion, paste and replay still
                        # reach the native control and its normal handlers.
                        if event.GetRawKeyCode() not in (8, 16, 17, 86, 0xA0, 0xA1, 0xE7):
                            return
                        if event.GetRawKeyCode() == keyboard_input.VK_V:
                            chords.append((event.ControlDown(), event.ShiftDown(), event.AltDown()))
                        event.Skip()
                    field.Bind(wx.EVT_KEY_DOWN, observe)
                    def observe_character(event):
                        if event.GetKeyCode() in (8, 22, ord("?")):
                            event.Skip()
                    field.Bind(wx.EVT_CHAR, observe_character)
                    def finish():
                        try:
                            self.assertEqual(field.GetValue(), "Expanded?")
                            self.assertEqual(chords, [(True, False, False)])
                            self.assertTrue(keyboard_input.user32.GetAsyncKeyState(shift) & 0x8000)
                        except BaseException as error:
                            errors.append(error)
                        target.EndModal(wx.ID_OK)
                    def paste():
                        try:
                            self.assertEqual(windows.get_foreground_window(), target.GetHandle())
                            self.assertTrue(keyboard_input.user32.GetAsyncKeyState(shift) & 0x8000)
                            # Exercise actual clipboard capture, publication,
                            # activation, deletion, Ctrl+V and Unicode replay.
                            pending.append(hotstring_expansion.expand_hotstring(
                                windows.get_window_identity(target.GetHandle()),
                                "Expanded", 6, "?", session=ClipboardPasteSession(),
                            ))
                            timers.append(wx.CallLater(80, finish))
                        except BaseException as error:
                            errors.append(error)
                            target.EndModal(wx.ID_ABORT)
                    def begin():
                        try:
                            self.assertTrue(windows.activate_window(target.GetHandle()))
                            field.SetFocus()
                            windows.user32.SetFocus(field.GetHandle())
                            field.SetInsertionPointEnd()
                            shift_sent.append(True)
                            inject_shift(0)
                            timers.append(wx.CallLater(30, paste))
                        except BaseException as error:
                            errors.append(error)
                            target.EndModal(wx.ID_ABORT)
                    timers.append(wx.CallLater(40, begin))
                    timeout = wx.CallLater(3000, target.EndModal, wx.ID_ABORT)
                    try:
                        returned = target.ShowModal()
                        if errors:
                            raise errors[0]
                        self.assertEqual(returned, wx.ID_OK)
                    finally:
                        timeout.Stop()
                        for timer in timers:
                            timer.Stop()
                        try:
                            if shift_sent:
                                inject_shift(keyboard_input.KEYEVENTF_KEYUP)
                        finally:
                            try:
                                for saved in pending:
                                    for attempt in range(3):
                                        try:
                                            saved.restore_clipboard()
                                            break
                                        except clipboard.ClipboardError:
                                            if attempt == 2:
                                                raise
                                            time.sleep(0.02)
                            finally:
                                target.Destroy()


if __name__ == "__main__":
    unittest.main()
