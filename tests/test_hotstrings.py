import unittest
import ctypes
from types import SimpleNamespace
from unittest.mock import patch

import hotstrings
from hotstrings import HotstringMatcher, KeyboardHook


class HotstringMatcherTestCase(unittest.TestCase):
    def setUp(self):
        self.matcher = HotstringMatcher()
        self.snippet = SimpleNamespace(hotstring="MfG")
        self.matcher.update((self.snippet,))

    def test_matches_with_exact_case_at_space(self):
        for character in "MfG":
            self.assertIsNone(self.matcher.character(character))
        self.assertIs(self.matcher.character(" "), self.snippet)

    def test_does_not_match_with_different_case(self):
        for value in ("mfg", "MFG"):
            with self.subTest(value=value):
                self.matcher.reset()
                for character in value:
                    self.assertIsNone(self.matcher.character(character))
                self.assertIsNone(self.matcher.character(" "))

    def test_does_not_match_inside_a_word(self):
        for character in "MfGFormular":
            self.assertIsNone(self.matcher.character(character))
        self.assertIsNone(self.matcher.character(" "))

    def test_matches_at_unicode_punctuation(self):
        for character in "MfG":
            self.matcher.character(character)
        self.assertIs(self.matcher.character("…"), self.snippet)

    def test_punctuation_can_be_part_of_user_chosen_hotstring(self):
        snippet = SimpleNamespace(hotstring=";mfg")
        self.matcher.update((snippet,))
        for character in ";mfg":
            self.assertIsNone(self.matcher.character(character))
        self.assertIs(self.matcher.character(" "), snippet)

    def test_backspace_updates_buffer(self):
        for character in "MfGX":
            self.matcher.character(character)
        self.matcher.backspace()
        self.assertIs(self.matcher.character("\t"), self.snippet)

    def test_update_resets_partial_input(self):
        for character in "Mf":
            self.matcher.character(character)
        self.matcher.update((self.snippet,))
        self.assertIsNone(self.matcher.character("G"))
        self.assertIsNone(self.matcher.character("\r"))


class KeyboardHookSmokeTestCase(unittest.TestCase):
    def test_native_hook_can_be_installed_and_removed(self):
        hook = KeyboardHook(lambda snippet, key: False)
        hook.start()
        self.addCleanup(hook.stop)
        self.assertIsNotNone(hook._handle)
        hook.stop()
        self.assertIsNone(hook._handle)

    def test_shift_key_alone_preserves_partial_hotstring(self):
        for shift_key in (
            hotstrings.VK_SHIFT,
            hotstrings.VK_LSHIFT,
            hotstrings.VK_RSHIFT,
        ):
            with self.subTest(shift_key=shift_key):
                hook = KeyboardHook(lambda snippet, key: False)
                snippet = SimpleNamespace(hotstring="MfG")
                hook.update((snippet,))
                hook._matcher.character("M")
                event = hotstrings.KBDLLHOOKSTRUCT(
                    shift_key, 0, 0, 0, 0
                )

                with (
                    patch.object(
                        hotstrings.user32,
                        "GetForegroundWindow",
                        return_value=123,
                    ),
                    patch.object(
                        hotstrings.user32,
                        "CallNextHookEx",
                        return_value=0,
                    ),
                ):
                    hook._foreground_window = 123
                    hook._hook_callback(
                        hotstrings.HC_ACTION,
                        hotstrings.WM_KEYDOWN,
                        ctypes.addressof(event),
                    )

                self.assertEqual(hook._matcher._buffer, "M")
                self.assertIsNone(hook._matcher.character("f"))
                self.assertIsNone(hook._matcher.character("G"))
                self.assertIs(hook._matcher.character(" "), snippet)

    def test_shift_state_is_applied_to_following_character(self):
        matches = []
        hook = KeyboardHook(
            lambda snippet, key: matches.append((snippet, key)) or True
        )
        snippet = SimpleNamespace(hotstring="M")
        hook.update((snippet,))
        shift_down = hotstrings.KBDLLHOOKSTRUCT(
            hotstrings.VK_LSHIFT, 0, 0, 0, 0
        )
        letter_down = hotstrings.KBDLLHOOKSTRUCT(ord("M"), 0, 0, 0, 0)
        shift_up = hotstrings.KBDLLHOOKSTRUCT(
            hotstrings.VK_LSHIFT, 0, 0, 0, 0
        )
        space_down = hotstrings.KBDLLHOOKSTRUCT(
            hotstrings.VK_SPACE, 0, 0, 0, 0
        )

        with (
            patch.object(
                hotstrings.user32,
                "GetForegroundWindow",
                return_value=123,
            ),
            patch.object(hotstrings.user32, "CallNextHookEx", return_value=0),
            patch.object(
                hook,
                "_translate",
                side_effect=("M", " "),
            ) as translate,
        ):
            hook._foreground_window = 123
            hook._hook_callback(
                hotstrings.HC_ACTION,
                hotstrings.WM_KEYDOWN,
                ctypes.addressof(shift_down),
            )
            hook._hook_callback(
                hotstrings.HC_ACTION,
                hotstrings.WM_KEYDOWN,
                ctypes.addressof(letter_down),
            )
            hook._hook_callback(
                hotstrings.HC_ACTION,
                hotstrings.WM_KEYUP,
                ctypes.addressof(shift_up),
            )
            result = hook._hook_callback(
                hotstrings.HC_ACTION,
                hotstrings.WM_KEYDOWN,
                ctypes.addressof(space_down),
            )

        self.assertEqual(
            translate.call_args_list[0].kwargs,
            {"shift_down": True},
        )
        self.assertEqual(
            translate.call_args_list[1].kwargs,
            {"shift_down": False},
        )
        self.assertEqual(matches, [(snippet, hotstrings.VK_SPACE)])
        self.assertEqual(result, 1)
