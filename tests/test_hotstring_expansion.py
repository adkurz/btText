import unittest
from unittest.mock import Mock, call, patch

from core.hotstrings import HotstringExpansionError
from platform_support import clipboard, hotstring_expansion
from platform_support.windows import WindowIdentity
from platform_support.clipboard_paste import ClipboardRestoreError, PendingPaste


TARGET = WindowIdentity(handle=123, thread_id=7, process_id=9)


class HotstringExpansionTestCase(unittest.TestCase):
    def test_suppressed_boundary_is_replayed_in_original_window(self):
        with (
            patch.object(
                hotstring_expansion.windows,
                "matches_window_identity",
                return_value=True,
            ),
            patch.object(
                hotstring_expansion.windows,
                "activate_window",
                return_value=True,
            ) as activate_window,
            patch.object(
                hotstring_expansion.keyboard_input,
                "send_virtual_key",
            ) as send_virtual_key,
        ):
            hotstring_expansion.replay_suppressed_boundary(TARGET, 0x20)

        activate_window.assert_called_once_with(123)
        send_virtual_key.assert_called_once_with(0x20)

    def test_suppressed_boundary_rejects_invalid_target(self):
        with (
            patch.object(
                hotstring_expansion.windows,
                "matches_window_identity",
                return_value=False,
            ),
            patch.object(
                hotstring_expansion.keyboard_input,
                "send_virtual_key",
            ) as send_virtual_key,
        ):
            with self.assertRaises(HotstringExpansionError) as raised:
                hotstring_expansion.replay_suppressed_boundary(TARGET, 0x20)

        self.assertEqual(raised.exception.code, "hotstring_target_window_missing")
        send_virtual_key.assert_not_called()

    def test_suppressed_boundary_reports_activation_failure(self):
        with (
            patch.object(
                hotstring_expansion.windows,
                "matches_window_identity",
                return_value=True,
            ),
            patch.object(
                hotstring_expansion.windows,
                "activate_window",
                return_value=False,
            ),
            patch.object(
                hotstring_expansion.keyboard_input,
                "send_virtual_key",
            ) as send_virtual_key,
        ):
            with self.assertRaises(HotstringExpansionError) as raised:
                hotstring_expansion.replay_suppressed_boundary(TARGET, 0x20)

        self.assertEqual(
            raised.exception.code,
            "hotstring_target_window_activation_failed",
        )
        send_virtual_key.assert_not_called()

    def _expand(self, boundary_key):
        pending = Mock(spec=PendingPaste)
        with (
            patch.object(
                hotstring_expansion.windows,
                "matches_window_identity",
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
                TARGET,
                "Expanded",
                3,
                boundary_key,
            )
        return result, pending, prepare, send_ctrl_v, send_virtual_key

    def test_boundary_key_is_replayed_when_requested(self):
        result, pending, prepare, send_ctrl_v, send_virtual_key = self._expand(0x20)

        self.assertIs(result, pending)
        prepare.assert_called_once_with("Expanded")
        send_ctrl_v.assert_called_once_with()
        self.assertEqual(
            send_virtual_key.call_args_list,
            [call(0x08, 3), call(0x20)],
        )

    def test_boundary_key_can_be_discarded(self):
        _result, _pending, _prepare, send_ctrl_v, send_virtual_key = self._expand(None)

        send_ctrl_v.assert_called_once_with()
        send_virtual_key.assert_called_once_with(0x08, 3)

    def test_invalid_target_is_rejected_before_preparing_clipboard(self):
        with (
            patch.object(
                hotstring_expansion.windows,
                "matches_window_identity",
                return_value=False,
            ),
            patch.object(PendingPaste, "prepare") as prepare,
        ):
            with self.assertRaises(HotstringExpansionError) as raised:
                hotstring_expansion.expand_hotstring(TARGET, "Expanded", 3, None)

        self.assertEqual(raised.exception.code, "hotstring_target_window_missing")
        self.assertEqual(str(raised.exception), "The active window no longer exists.")
        prepare.assert_not_called()

    def test_activation_failure_restores_pending_paste(self):
        pending = Mock(spec=PendingPaste)
        with (
            patch.object(
                hotstring_expansion.windows,
                "matches_window_identity",
                return_value=True,
            ),
            patch.object(PendingPaste, "prepare", return_value=pending),
            patch.object(
                hotstring_expansion.windows,
                "activate_window",
                return_value=False,
            ),
        ):
            with self.assertRaises(HotstringExpansionError) as raised:
                hotstring_expansion.expand_hotstring(TARGET, "Expanded", 3, None)

        self.assertEqual(
            raised.exception.code,
            "hotstring_target_window_activation_failed",
        )
        pending.restore_clipboard.assert_called_once_with()

    def test_input_failure_restores_pending_paste(self):
        pending = Mock(spec=PendingPaste)
        with (
            patch.object(
                hotstring_expansion.windows,
                "matches_window_identity",
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
                hotstring_expansion.expand_hotstring(TARGET, "Expanded", 3, None)

        pending.restore_clipboard.assert_called_once_with()

    def test_input_and_restore_failures_are_both_preserved(self):
        operation_error = clipboard.ClipboardError("input failed")
        restore_error = clipboard.ClipboardError("restore failed")
        pending = Mock(spec=PendingPaste)
        pending.restore_clipboard.side_effect = restore_error
        with (
            patch.object(
                hotstring_expansion.windows,
                "matches_window_identity",
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
                side_effect=operation_error,
            ),
        ):
            with self.assertRaises(ClipboardRestoreError) as raised:
                hotstring_expansion.expand_hotstring(
                    TARGET,
                    "Expanded",
                    3,
                    None,
                )

        self.assertIs(raised.exception.operation_error, operation_error)
        self.assertIs(raised.exception.restore_error, restore_error)
        self.assertIs(raised.exception.__cause__, operation_error)
