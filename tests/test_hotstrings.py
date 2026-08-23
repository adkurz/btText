import unittest
import ctypes
import threading
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
        self.assertNotEqual(hook._thread_id, threading.get_native_id())
        hook.stop()
        self.assertIsNone(hook._handle)

    def test_hook_can_be_started_again_after_stop(self):
        hook = KeyboardHook(lambda snippet, key: False)
        self.addCleanup(hook.stop)

        hook.start()
        first_thread = hook._thread
        hook.stop()
        hook.start()

        self.assertIsNot(hook._thread, first_thread)
        self.assertTrue(hook._thread.is_alive())

    def test_focused_child_change_discards_partial_hotstring(self):
        hook = KeyboardHook(lambda snippet, key: False)
        hook.update({"hello": object()})
        hook._matcher.character("h")
        hook._input_context = (123, 456, 1)
        event = hotstrings.KBDLLHOOKSTRUCT(ord("E"), 0, 0, 0, 0)

        with (
            patch.object(
                hook,
                "_get_input_context",
                return_value=(123, 789, 1),
            ),
            patch.object(hook, "_translate", return_value="e"),
            patch.object(hotstrings.user32, "CallNextHookEx", return_value=0),
        ):
            hook._hook_callback(
                hotstrings.HC_ACTION,
                hotstrings.WM_KEYDOWN,
                ctypes.addressof(event),
            )

        self.assertEqual(hook._matcher._buffer, "e")

    def test_callback_failure_is_contained_and_chained(self):
        hook = KeyboardHook(lambda snippet, key: False)

        with (
            patch.object(hook, "_process_hook_event", side_effect=RuntimeError),
            patch.object(
                hotstrings.user32,
                "CallNextHookEx",
                return_value=17,
            ) as call_next,
            self.assertLogs("bttext.hotstrings", level="ERROR"),
        ):
            result = hook._hook_callback(0, 0, 0)

        self.assertEqual(result, 17)
        call_next.assert_called_once()

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
                    hook._input_context = (123, None, None)
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
            hook._input_context = (123, None, None)
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
            {"shift_down": True, "keyboard_layout": None},
        )
        self.assertEqual(
            translate.call_args_list[1].kwargs,
            {"shift_down": False, "keyboard_layout": None},
        )
        self.assertEqual(matches, [(snippet, hotstrings.VK_SPACE)])
        self.assertEqual(result, 1)
