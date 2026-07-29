import unittest
from unittest.mock import Mock, patch

from platform_support import clipboard, clipboard_paste
from platform_support.clipboard_paste import PendingPaste


class RecordingClipboardSnapshot:
    def __init__(self):
        self.close_calls = 0
        self.restore_calls = 0

    def close(self):
        self.close_calls += 1

    def restore(self):
        self.restore_calls += 1


class ClipboardPasteCompatibilityTestCase(unittest.TestCase):
    def test_paste_error_remains_compatible_with_clipboard_error(self):
        self.assertIs(clipboard_paste.PasteError, clipboard.ClipboardError)


class PendingPasteTestCase(unittest.TestCase):
    def test_discard_snapshot_releases_saved_clipboard_data(self):
        snapshot = RecordingClipboardSnapshot()
        pending = PendingPaste(snapshot, b"marker", "snippet")

        pending.discard_snapshot()

        self.assertEqual(snapshot.close_calls, 1)

    def test_restore_uses_marker_when_it_is_still_available(self):
        snapshot = RecordingClipboardSnapshot()
        pending = PendingPaste(snapshot, b"marker", "snippet")

        with (
            patch.object(clipboard_paste, "_open_clipboard"),
            patch.object(
                clipboard_paste,
                "_read_clipboard_bytes",
                side_effect=[b"marker", None],
            ),
            patch.object(clipboard_paste.user32, "CloseClipboard"),
        ):
            pending.restore_clipboard()

        self.assertEqual(snapshot.restore_calls, 1)
        self.assertEqual(snapshot.close_calls, 0)

    def test_restore_preserves_a_genuine_new_clipboard_value(self):
        snapshot = RecordingClipboardSnapshot()
        pending = PendingPaste(snapshot, b"marker", "snippet")

        with (
            patch.object(clipboard_paste, "_open_clipboard"),
            patch.object(
                clipboard_paste,
                "_read_clipboard_bytes",
                side_effect=[
                    b"different marker",
                    "new value\0".encode("utf-16-le"),
                ],
            ),
            patch.object(clipboard_paste.user32, "CloseClipboard"),
        ):
            pending.restore_clipboard()

        self.assertEqual(snapshot.restore_calls, 0)
        self.assertEqual(snapshot.close_calls, 1)

    def test_restore_accepts_unchanged_text_when_target_removed_marker(self):
        snapshot = RecordingClipboardSnapshot()
        pending = PendingPaste(snapshot, b"marker", "snippet")

        with (
            patch.object(clipboard_paste, "_open_clipboard"),
            patch.object(
                clipboard_paste,
                "_read_clipboard_bytes",
                side_effect=[None, "snippet\0".encode("utf-16-le")],
            ),
            patch.object(clipboard_paste.user32, "CloseClipboard"),
        ):
            pending.restore_clipboard()

        self.assertEqual(snapshot.restore_calls, 1)
        self.assertEqual(snapshot.close_calls, 0)


class PasteTextTestCase(unittest.TestCase):
    def test_invalid_target_is_rejected_before_clipboard_replacement(self):
        with (
            patch.object(
                clipboard_paste.windows,
                "is_valid_window",
                return_value=False,
            ),
            patch.object(
                clipboard_paste,
                "_replace_clipboard",
            ) as replace_clipboard,
        ):
            with self.assertRaises(clipboard.ClipboardError):
                clipboard_paste.paste_text(123, "Text")

        replace_clipboard.assert_not_called()

    def test_activation_failure_restores_replaced_clipboard(self):
        snapshot = RecordingClipboardSnapshot()
        with (
            patch.object(
                clipboard_paste.windows,
                "is_valid_window",
                return_value=True,
            ),
            patch.object(
                clipboard_paste,
                "_replace_clipboard",
                return_value=snapshot,
            ),
            patch.object(
                clipboard_paste.windows,
                "activate_window",
                return_value=False,
            ),
            patch.object(
                PendingPaste,
                "restore_clipboard",
            ) as restore_clipboard,
        ):
            with self.assertRaises(clipboard.ClipboardError):
                clipboard_paste.paste_text(123, "Text")

        restore_clipboard.assert_called_once_with()


class HotstringExpansionTestCase(unittest.TestCase):
    def _expand(self, boundary_key):
        snapshot = RecordingClipboardSnapshot()
        with (
            patch.object(
                clipboard_paste.windows,
                "is_valid_window",
                return_value=True,
            ),
            patch.object(
                clipboard_paste, "_replace_clipboard", return_value=snapshot
            ),
            patch.object(
                clipboard_paste.windows,
                "activate_window",
                return_value=True,
            ),
            patch.object(
                clipboard_paste.keyboard_input,
                "send_ctrl_v",
            ) as send_ctrl_v,
            patch.object(
                clipboard_paste.keyboard_input,
                "send_virtual_key",
            ) as send_virtual_key,
        ):
            pending = clipboard_paste.expand_hotstring(
                123, "Expanded", 3, boundary_key
            )
        return pending, send_ctrl_v, send_virtual_key

    def test_boundary_key_is_replayed_when_requested(self):
        pending, send_ctrl_v, send_virtual_key = self._expand(0x20)

        self.assertIsInstance(pending, PendingPaste)
        send_ctrl_v.assert_called_once_with()
        self.assertEqual(
            send_virtual_key.call_args_list,
            [unittest.mock.call(0x08, 3), unittest.mock.call(0x20)],
        )

    def test_boundary_key_can_be_discarded(self):
        _pending, send_ctrl_v, send_virtual_key = self._expand(None)

        send_ctrl_v.assert_called_once_with()
        send_virtual_key.assert_called_once_with(0x08, 3)


if __name__ == "__main__":
    unittest.main()
