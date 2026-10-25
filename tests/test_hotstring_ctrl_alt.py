"""Recognize layout-defined Ctrl+Alt text without matching shortcuts."""

import ctypes
import unittest
from ctypes import wintypes
from unittest.mock import Mock, patch

from platform_support import hotstrings


class CtrlAltTextTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        get_layouts = hotstrings.user32.GetKeyboardLayoutList
        get_layouts.argtypes = (ctypes.c_int, ctypes.POINTER(wintypes.HKL))
        get_layouts.restype = ctypes.c_int
        layouts = (wintypes.HKL * get_layouts(0, None))()
        count = get_layouts(len(layouts), layouts)
        cls.layouts = {
            layout & 0xFFFFFFFF: layout for layout in layouts[:count]
        }

    def layout(self, identifier):
        if identifier not in self.layouts:
            self.skipTest(f"Keyboard layout {identifier:08X} is not loaded")
        return self.layouts[identifier]

    def dispatch(self, layout, held, key, scan=0, flags=0):
        matched = Mock(return_value=True)
        hook = hotstrings.KeyboardHook(matched)
        snippet = object()
        hook.update({"x": snippet})
        context = (123, 456, layout)
        hook._input_context = context
        with (
            patch.object(hook, "_get_input_context", return_value=context),
            patch.object(hotstrings.user32, "GetAsyncKeyState",
                         side_effect=lambda key: 0x8000 if key in held else 0),
            # Leave the hook thread's keyboard snapshot empty. Translation
            # must use the modifiers supplied for the observed physical input.
            patch.object(hotstrings.user32, "GetKeyboardState", return_value=True),
            patch.object(hotstrings.user32, "CallNextHookEx", return_value=37),
        ):
            first = hotstrings.KBDLLHOOKSTRUCT(ord("X"), 0x2D, 0, 0, 0)
            with patch.object(hotstrings.user32, "GetAsyncKeyState", return_value=0):
                hook._hook_callback(0, hotstrings.WM_KEYDOWN, ctypes.addressof(first))
            self.assertEqual(hook._matcher._buffer, "x")
            for modifier in held:
                event = hotstrings.KBDLLHOOKSTRUCT(modifier, 0, 0, 0, 0)
                self.assertEqual(hook._hook_callback(
                    0, hotstrings.WM_KEYDOWN, ctypes.addressof(event),
                ), 37)
            event = hotstrings.KBDLLHOOKSTRUCT(key, scan, flags, 0, 0)
            result = hook._hook_callback(
                0, hotstrings.WM_KEYDOWN, ctypes.addressof(event),
            )
        return result, matched, snippet, hook

    def test_german_backslash_ends_hotstring_with_ctrl_alt_or_altgr(self):
        layout = self.layout(0x04070407)
        for control in (hotstrings.VK_LCONTROL, hotstrings.VK_RCONTROL):
            for alt in (hotstrings.VK_LMENU, hotstrings.VK_RMENU):
                for flags in (0, hotstrings.LLKHF_ALTDOWN):
                    with self.subTest(control=control, alt=alt, flags=flags):
                        result, matched, snippet, hook = self.dispatch(
                            layout, (control, alt), 0xDB, 0x0C, flags,
                        )
                        self.assertEqual(result, 1)
                        matched.assert_called_once()
                        self.assertEqual(matched.call_args.args[:2], (snippet, "\\"))
                        self.assertFalse(matched.call_args.args[2].cancelled.is_set())
                        self.assertEqual(hook._matcher._buffer, "")

    def test_other_german_ctrl_alt_punctuation_remains_layout_defined(self):
        layout = self.layout(0x04070407)
        for key, scan, expected in (
            (ord("Q"), 0x10, "@"),
            (ord("7"), 0x08, "{"),
            (ord("8"), 0x09, "["),
            (ord("9"), 0x0A, "]"),
            (ord("0"), 0x0B, "}"),
            (0xE2, 0x56, "|"),
        ):
            with self.subTest(expected=expected):
                result, matched, snippet, _hook = self.dispatch(
                    layout, (hotstrings.VK_LCONTROL, hotstrings.VK_LMENU),
                    key, scan, hotstrings.LLKHF_ALTDOWN,
                )
                self.assertEqual(result, 1)
                self.assertEqual(matched.call_args.args[:2], (snippet, expected))

    def test_ctrl_alt_shortcuts_are_forwarded_and_clear_partial_input(self):
        for identifier in (0x04070407, 0x04090409):
            layout = self.layout(identifier)
            for key in (ord("C"), hotstrings.VK_SPACE, hotstrings.VK_TAB,
                        hotstrings.VK_RETURN, hotstrings.VK_BACK):
                with self.subTest(layout=identifier, key=key):
                    result, matched, _snippet, hook = self.dispatch(
                        layout, (hotstrings.VK_LCONTROL, hotstrings.VK_LMENU),
                        key, flags=hotstrings.LLKHF_ALTDOWN,
                    )
                    self.assertEqual(result, 37)
                    matched.assert_not_called()
                    self.assertEqual(hook._matcher._buffer, "")

    def test_us_ctrl_alt_has_no_german_backslash_mapping(self):
        result, matched, _snippet, hook = self.dispatch(
            self.layout(0x04090409),
            (hotstrings.VK_LCONTROL, hotstrings.VK_LMENU), 0xDB, 0x0C,
            hotstrings.LLKHF_ALTDOWN,
        )
        self.assertEqual(result, 37)
        matched.assert_not_called()
        self.assertEqual(hook._matcher._buffer, "")

    def test_ctrl_alt_control_characters_cannot_end_a_hotstring(self):
        for character in ("\r", "\t", " ", "\x1c"):
            with self.subTest(character=character):
                with patch.object(
                    hotstrings.KeyboardHook, "_translate",
                    side_effect=("x", character),
                ):
                    result, matched, _snippet, hook = self.dispatch(
                        456, (hotstrings.VK_LCONTROL, hotstrings.VK_LMENU),
                        ord("C"), flags=hotstrings.LLKHF_ALTDOWN,
                    )
                self.assertEqual(result, 37)
                matched.assert_not_called()
                self.assertEqual(hook._matcher._buffer, "")

    def test_windows_key_prevents_ctrl_alt_text_matching(self):
        result, matched, _snippet, hook = self.dispatch(
            self.layout(0x04070407),
            (hotstrings.VK_LCONTROL, hotstrings.VK_LMENU, hotstrings.VK_LWIN),
            0xDB, 0x0C, hotstrings.LLKHF_ALTDOWN,
        )
        self.assertEqual(result, 37)
        matched.assert_not_called()
        self.assertEqual(hook._matcher._buffer, "")


if __name__ == "__main__":
    unittest.main()
