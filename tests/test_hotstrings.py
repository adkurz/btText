import unittest
import ctypes
from types import SimpleNamespace
from unittest.mock import patch

from platform_support import hotstrings
from platform_support.hotstrings import KeyboardHook


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
                hook.update({"MfG": snippet})
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
        hook.update({"M": snippet})
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
