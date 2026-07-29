import unittest
from unittest.mock import Mock, call, patch

from platform_support import clipboard, hotstring_expansion
from platform_support.clipboard_paste import PendingPaste


class HotstringExpansionTestCase(unittest.TestCase):
    def _expand(self, boundary_key):
        pending = Mock(spec=PendingPaste)
        with (
            patch.object(
                hotstring_expansion.windows,
                "is_valid_window",
                return_value=True,
            ),
            patch.object(
                PendingPaste,
                "prepare",
                return_value=pending,
            ) as prepare,
            patch.object(
                hotstring_expansion.windows,
                "activate_window",
                return_value=True,
            ),
            patch.object(
                hotstring_expansion.keyboard_input,
                "send_ctrl_v",
            ) as send_ctrl_v,
            patch.object(
                hotstring_expansion.keyboard_input,
                "send_virtual_key",
            ) as send_virtual_key,
        ):
            result = hotstring_expansion.expand_hotstring(
                123,
                "Expanded",
                3,
                boundary_key,
            )
        return result, pending, prepare, send_ctrl_v, send_virtual_key

    def test_boundary_key_is_replayed_when_requested(self):
        result, pending, prepare, send_ctrl_v, send_virtual_key = self._expand(
            0x20
        )

        self.assertIs(result, pending)
        prepare.assert_called_once_with("Expanded")
        send_ctrl_v.assert_called_once_with()
        self.assertEqual(
            send_virtual_key.call_args_list,
            [call(0x08, 3), call(0x20)],
        )

    def test_boundary_key_can_be_discarded(self):
        _result, _pending, _prepare, send_ctrl_v, send_virtual_key = (
            self._expand(None)
        )

        send_ctrl_v.assert_called_once_with()
        send_virtual_key.assert_called_once_with(0x08, 3)

    def test_invalid_target_is_rejected_before_preparing_clipboard(self):
        with (
            patch.object(
                hotstring_expansion.windows,
                "is_valid_window",
                return_value=False,
            ),
            patch.object(PendingPaste, "prepare") as prepare,
        ):
            with self.assertRaises(clipboard.ClipboardError):
                hotstring_expansion.expand_hotstring(123, "Expanded", 3, None)

        prepare.assert_not_called()

    def test_activation_failure_restores_pending_paste(self):
        pending = Mock(spec=PendingPaste)
        with (
            patch.object(
                hotstring_expansion.windows,
                "is_valid_window",
                return_value=True,
            ),
            patch.object(PendingPaste, "prepare", return_value=pending),
            patch.object(
                hotstring_expansion.windows,
                "activate_window",
                return_value=False,
            ),
        ):
            with self.assertRaises(clipboard.ClipboardError):
                hotstring_expansion.expand_hotstring(123, "Expanded", 3, None)

        pending.restore_clipboard.assert_called_once_with()

    def test_input_failure_restores_pending_paste(self):
        pending = Mock(spec=PendingPaste)
        with (
            patch.object(
                hotstring_expansion.windows,
                "is_valid_window",
                return_value=True,
            ),
            patch.object(PendingPaste, "prepare", return_value=pending),
            patch.object(
                hotstring_expansion.windows,
                "activate_window",
                return_value=True,
            ),
            patch.object(
                hotstring_expansion.keyboard_input,
                "send_virtual_key",
                side_effect=clipboard.ClipboardError("input failed"),
            ),
        ):
            with self.assertRaisesRegex(
                clipboard.ClipboardError,
                "input failed",
            ):
                hotstring_expansion.expand_hotstring(123, "Expanded", 3, None)

        pending.restore_clipboard.assert_called_once_with()
