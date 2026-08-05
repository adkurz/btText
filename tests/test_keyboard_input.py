import ctypes
import unittest
from unittest.mock import patch

from platform_support import clipboard, keyboard_input


class KeyboardInputTestCase(unittest.TestCase):
    def test_input_structure_has_required_64_bit_windows_size(self):
        self.assertEqual(ctypes.sizeof(keyboard_input.INPUT), 40)

    def test_ctrl_v_sends_balanced_key_sequence(self):
        captured = []

        def record_inputs(count, inputs, input_size):
            captured.extend(
                (inputs[index].ki.wVk, inputs[index].ki.dwFlags)
                for index in range(count)
            )
            self.assertEqual(input_size, ctypes.sizeof(keyboard_input.INPUT))
            return count

        with patch.object(
            keyboard_input.user32,
            "SendInput",
            side_effect=record_inputs,
        ):
            keyboard_input.send_ctrl_v()

        self.assertEqual(
            captured,
            [
                (keyboard_input.VK_CONTROL, 0),
                (keyboard_input.VK_V, 0),
                (keyboard_input.VK_V, keyboard_input.KEYEVENTF_KEYUP),
                (
                    keyboard_input.VK_CONTROL,
                    keyboard_input.KEYEVENTF_KEYUP,
                ),
            ],
        )

    def test_repeated_virtual_key_sends_down_and_up_for_each_press(self):
        captured = []

        def record_inputs(count, inputs, _input_size):
            captured.extend(
                (inputs[index].ki.wVk, inputs[index].ki.dwFlags)
                for index in range(count)
            )
            return count

        with patch.object(
            keyboard_input.user32,
            "SendInput",
            side_effect=record_inputs,
        ):
            keyboard_input.send_virtual_key(0x08, repetitions=2)

        self.assertEqual(
            captured,
            [
                (0x08, 0),
                (0x08, keyboard_input.KEYEVENTF_KEYUP),
                (0x08, 0),
                (0x08, keyboard_input.KEYEVENTF_KEYUP),
            ],
        )

    def test_partial_native_send_raises_clipboard_error(self):
        with patch.object(
            keyboard_input.user32,
            "SendInput",
            return_value=3,
        ):
            with self.assertRaises(clipboard.ClipboardError):
                keyboard_input.send_ctrl_v()

    @patch("platform_support.keyboard_input.send_virtual_key")
    def test_move_cursor_left_sends_left_arrow_repetitions(self, send_virtual_key):
        keyboard_input.move_cursor_left(3)

        send_virtual_key.assert_called_once_with(keyboard_input.VK_LEFT, 3)

    @patch("platform_support.keyboard_input.send_virtual_key")
    def test_zero_cursor_offset_sends_no_input(self, send_virtual_key):
        keyboard_input.move_cursor_left(0)

        send_virtual_key.assert_not_called()
