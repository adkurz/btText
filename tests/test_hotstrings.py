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
                hotstrings.user32,
                "GetAsyncKeyState",
                side_effect=lambda key: (
                    0x8000
                    if key in hotstrings.SHIFT_KEYS and shift_state["down"]
                    else 0
                ),
            ),
            patch.object(
                hook,
                "_translate",
                side_effect=("M", " "),
            ) as translate,
        ):
            shift_state = {"down": True}
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
            shift_state["down"] = False
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
            {
                "shift_down": True,
                "altgr_down": False,
                "keyboard_layout": None,
            },
        )
        self.assertEqual(
            translate.call_args_list[1].kwargs,
            {
                "shift_down": False,
                "altgr_down": False,
                "keyboard_layout": None,
            },
        )
        self.assertEqual(matches, [(snippet, hotstrings.VK_SPACE)])
        self.assertEqual(result, 1)

    def test_all_modifier_events_bypass_matcher_lock_and_are_forwarded(self):
        modifier_keys = (
            hotstrings.VK_SHIFT,
            hotstrings.VK_LSHIFT,
            hotstrings.VK_RSHIFT,
            hotstrings.VK_CONTROL,
            hotstrings.VK_LCONTROL,
            hotstrings.VK_RCONTROL,
            hotstrings.VK_MENU,
            hotstrings.VK_LMENU,
            hotstrings.VK_RMENU,
            hotstrings.VK_LWIN,
            hotstrings.VK_RWIN,
        )
        messages = (
            hotstrings.WM_KEYDOWN,
            hotstrings.WM_KEYUP,
            hotstrings.WM_SYSKEYDOWN,
            hotstrings.WM_SYSKEYUP,
        )
        for modifier_key in modifier_keys:
            for message in messages:
                with self.subTest(modifier_key=modifier_key, message=message):
                    hook = KeyboardHook(lambda snippet, key: False)
                    event = hotstrings.KBDLLHOOKSTRUCT(
                        modifier_key, 0, 0, 0, 0
                    )
                    with (
                        patch.object(
                            hotstrings.user32,
                            "CallNextHookEx",
                            return_value=37,
                        ) as call_next,
                        patch.object(
                            hook,
                            "_process_hook_event_locked",
                        ) as process_locked,
                    ):
                        result = hook._hook_callback(
                            hotstrings.HC_ACTION,
                            message,
                            ctypes.addressof(event),
                        )

                    self.assertEqual(result, 37)
                    call_next.assert_called_once_with(
                        hook._handle,
                        hotstrings.HC_ACTION,
                        message,
                        ctypes.addressof(event),
                    )
                    process_locked.assert_not_called()

    def test_non_text_modifier_chord_discards_partial_hotstring(self):
        for modifier_key in (
            hotstrings.VK_LCONTROL,
            hotstrings.VK_LMENU,
            hotstrings.VK_LWIN,
        ):
            with self.subTest(modifier_key=modifier_key):
                hook = KeyboardHook(lambda snippet, key: False)
                hook.update({"hello": object()})
                hook._matcher.character("h")
                hook._input_context = (123, None, None)
                modifier_down = hotstrings.KBDLLHOOKSTRUCT(
                    modifier_key, 0, 0, 0, 0
                )
                letter_down = hotstrings.KBDLLHOOKSTRUCT(
                    ord("E"),
                    0,
                    (
                        hotstrings.LLKHF_ALTDOWN
                        if modifier_key == hotstrings.VK_LMENU
                        else 0
                    ),
                    0,
                    0,
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
                    patch.object(
                        hotstrings.user32,
                        "GetAsyncKeyState",
                        side_effect=lambda key: (
                            0x8000 if key == modifier_key else 0
                        ),
                    ),
                    patch.object(hook, "_translate") as translate,
                ):
                    hook._hook_callback(
                        hotstrings.HC_ACTION,
                        hotstrings.WM_KEYDOWN,
                        ctypes.addressof(modifier_down),
                    )
                    hook._hook_callback(
                        hotstrings.HC_ACTION,
                        hotstrings.WM_KEYDOWN,
                        ctypes.addressof(letter_down),
                    )

                self.assertEqual(hook._matcher._buffer, "")
                translate.assert_not_called()

    def test_control_events_are_forwarded_without_persistent_state(self):
        for down_key, up_key in (
            (hotstrings.VK_LCONTROL, hotstrings.VK_LCONTROL),
            (hotstrings.VK_CONTROL, hotstrings.VK_LCONTROL),
            (hotstrings.VK_LCONTROL, hotstrings.VK_CONTROL),
            (hotstrings.VK_RCONTROL, hotstrings.VK_CONTROL),
        ):
            with self.subTest(down_key=down_key, up_key=up_key):
                hook = KeyboardHook(lambda snippet, key: False)
                hook.update({"e": object()})
                hook._input_context = (123, None, None)
                control_down = hotstrings.KBDLLHOOKSTRUCT(
                    down_key, 0, 0, 0, 0
                )
                control_up = hotstrings.KBDLLHOOKSTRUCT(up_key, 0, 0, 0, 0)
                letter_down = hotstrings.KBDLLHOOKSTRUCT(
                    ord("E"), 0, 0, 0, 0
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
                        return_value=37,
                    ) as call_next,
                    patch.object(
                        hook,
                        "_translate",
                        return_value="e",
                    ) as translate,
                ):
                    down_result = hook._hook_callback(
                        hotstrings.HC_ACTION,
                        hotstrings.WM_KEYDOWN,
                        ctypes.addressof(control_down),
                    )
                    up_result = hook._hook_callback(
                        hotstrings.HC_ACTION,
                        hotstrings.WM_KEYUP,
                        ctypes.addressof(control_up),
                    )
                    hook._hook_callback(
                        hotstrings.HC_ACTION,
                        hotstrings.WM_KEYDOWN,
                        ctypes.addressof(letter_down),
                    )

                self.assertEqual(down_result, 37)
                self.assertEqual(up_result, 37)
                self.assertEqual(call_next.call_count, 3)
                self.assertEqual(hook._matcher._buffer, "e")
                translate.assert_called_once_with(
                    ord("E"),
                    0,
                    shift_down=False,
                    altgr_down=False,
                    keyboard_layout=None,
                )

    def test_right_control_copy_discards_partial_input_and_is_forwarded(self):
        hook = KeyboardHook(lambda snippet, key: False)
        hook.update({"hello": object()})
        hook._matcher.character("h")
        hook._input_context = (123, None, None)
        control_down = hotstrings.KBDLLHOOKSTRUCT(
            hotstrings.VK_RCONTROL, 0, 0, 0, 0
        )
        copy_down = hotstrings.KBDLLHOOKSTRUCT(ord("C"), 0, 0, 0, 0)
        control_up = hotstrings.KBDLLHOOKSTRUCT(
            hotstrings.VK_RCONTROL, 0, 0, 0, 0
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
                return_value=37,
            ) as call_next,
            patch.object(
                hotstrings.user32,
                "GetAsyncKeyState",
                side_effect=lambda key: (
                    0x8000 if key == hotstrings.VK_RCONTROL else 0
                ),
            ),
            patch.object(hook, "_translate") as translate,
        ):
            down_result = hook._hook_callback(
                hotstrings.HC_ACTION,
                hotstrings.WM_KEYDOWN,
                ctypes.addressof(control_down),
            )
            copy_result = hook._hook_callback(
                hotstrings.HC_ACTION,
                hotstrings.WM_KEYDOWN,
                ctypes.addressof(copy_down),
            )
            up_result = hook._hook_callback(
                hotstrings.HC_ACTION,
                hotstrings.WM_KEYUP,
                ctypes.addressof(control_up),
            )

        self.assertEqual((down_result, copy_result, up_result), (37, 37, 37))
        self.assertEqual(call_next.call_count, 3)
        self.assertEqual(hook._matcher._buffer, "")
        translate.assert_not_called()

    def test_altgr_remains_available_for_layout_dependent_text(self):
        hook = KeyboardHook(lambda snippet, key: False)
        hook.update({"a@": object()})
        hook._matcher.character("a")
        hook._input_context = (123, None, 456)
        control_down = hotstrings.KBDLLHOOKSTRUCT(
            hotstrings.VK_LCONTROL, 0, 0, 0, 0
        )
        right_alt_down = hotstrings.KBDLLHOOKSTRUCT(
            hotstrings.VK_RMENU, 0, 0, 0, 0
        )
        character_down = hotstrings.KBDLLHOOKSTRUCT(
            ord("Q"), 0, hotstrings.LLKHF_ALTDOWN, 0, 0
        )

        with (
            patch.object(
                hook,
                "_get_input_context",
                return_value=(123, None, 456),
            ),
            patch.object(hotstrings.user32, "CallNextHookEx", return_value=0),
            patch.object(
                hotstrings.user32,
                "GetAsyncKeyState",
                side_effect=lambda key: (
                    0x8000
                    if key
                    in (hotstrings.VK_LCONTROL, hotstrings.VK_RMENU)
                    else 0
                ),
            ),
            patch.object(hook, "_translate", return_value="@") as translate,
        ):
            for event in (control_down, right_alt_down, character_down):
                hook._hook_callback(
                    hotstrings.HC_ACTION,
                    hotstrings.WM_KEYDOWN,
                    ctypes.addressof(event),
                )

        self.assertEqual(hook._matcher._buffer, "a@")
        translate.assert_called_once_with(
            ord("Q"),
            0,
            shift_down=False,
            altgr_down=True,
            keyboard_layout=456,
        )

    def test_translate_applies_canonical_altgr_keyboard_state(self):
        observed_state = {}

        def translate_key(
            virtual_key,
            scan_code,
            state,
            buffer,
            buffer_size,
            flags,
            keyboard_layout,
        ):
            observed_state.update(
                control=state[hotstrings.VK_CONTROL],
                left_control=state[hotstrings.VK_LCONTROL],
                alt=state[hotstrings.VK_MENU],
                right_alt=state[hotstrings.VK_RMENU],
            )
            buffer.value = "@"
            return 1

        with (
            patch.object(
                hotstrings.user32,
                "GetKeyboardState",
                return_value=True,
            ),
            patch.object(
                hotstrings.user32,
                "ToUnicodeEx",
                side_effect=translate_key,
            ),
        ):
            result = KeyboardHook._translate(
                ord("Q"),
                16,
                altgr_down=True,
                keyboard_layout=456,
            )

        self.assertEqual(result, "@")
        self.assertEqual(
            observed_state,
            {
                "control": 0x80,
                "left_control": 0x80,
                "alt": 0x80,
                "right_alt": 0x80,
            },
        )
