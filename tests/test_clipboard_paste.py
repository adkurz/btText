import unittest
from unittest.mock import Mock, patch

from platform_support import clipboard, clipboard_paste
from platform_support.clipboard_paste import ClipboardRestoreError, PendingPaste


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
    def test_prepare_excludes_temporary_text_from_history_and_cloud(self):
        snapshot = RecordingClipboardSnapshot()

        with (
            patch.object(
                clipboard_paste.ClipboardSnapshot,
                "capture",
                return_value=snapshot,
            ),
            patch.object(clipboard_paste, "_open_clipboard"),
            patch.object(
                clipboard_paste.user32,
                "EmptyClipboard",
                return_value=True,
            ),
            patch.object(clipboard_paste.user32, "CloseClipboard"),
            patch.object(clipboard_paste, "_set_clipboard_text"),
            patch.object(clipboard_paste, "_set_clipboard_data"),
            patch.object(
                clipboard_paste,
                "_exclude_current_item_from_history_and_cloud",
            ) as exclude_from_storage,
        ):
            PendingPaste.prepare("private snippet")

        exclude_from_storage.assert_called_once_with()

    def test_prepare_replaces_clipboard_with_generated_marker(self):
        snapshot = RecordingClipboardSnapshot()
        marker = b"generated marker"

        with (
            patch.object(
                clipboard_paste.uuid,
                "uuid4",
                return_value=Mock(bytes=marker),
            ),
            patch.object(
                clipboard_paste,
                "_replace_clipboard",
                return_value=snapshot,
            ) as replace_clipboard,
        ):
            pending = PendingPaste.prepare("snippet")

        replace_clipboard.assert_called_once_with("snippet", marker)
        self.assertIs(pending._snapshot, snapshot)
        self.assertEqual(pending._marker, marker)
        self.assertEqual(pending._pasted_text, "snippet")

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
                return_value=b"different marker",
            ),
            patch.object(
                clipboard_paste,
                "_read_open_clipboard_text",
                return_value="new value",
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
                return_value=None,
            ),
            patch.object(
                clipboard_paste,
                "_read_open_clipboard_text",
                return_value="snippet",
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

    def test_activation_and_restore_failures_are_both_preserved(self):
        restore_error = clipboard.ClipboardError("restore failed")
        with (
            patch.object(
                clipboard_paste.windows,
                "is_valid_window",
                return_value=True,
            ),
            patch.object(
                clipboard_paste,
                "_replace_clipboard",
                return_value=RecordingClipboardSnapshot(),
            ),
            patch.object(
                clipboard_paste.windows,
                "activate_window",
                return_value=False,
            ),
            patch.object(
                PendingPaste,
                "restore_clipboard",
                side_effect=restore_error,
            ),
        ):
            with self.assertRaises(ClipboardRestoreError) as raised:
                clipboard_paste.paste_text(123, "Text")

        self.assertRegex(str(raised.exception), "could not be activated")
        self.assertRegex(str(raised.exception), "restore failed")
        self.assertIs(
            raised.exception.__cause__,
            raised.exception.operation_error,
        )
        self.assertIs(raised.exception.restore_error, restore_error)

    def test_replacement_failure_restores_original_snapshot(self):
        snapshot = RecordingClipboardSnapshot()
        with (
            patch.object(
                clipboard_paste.ClipboardSnapshot,
                "capture",
                return_value=snapshot,
            ),
            patch.object(
                clipboard_paste,
                "_open_clipboard",
            ),
            patch.object(
                clipboard_paste.user32,
                "EmptyClipboard",
                return_value=True,
            ),
            patch.object(
                clipboard_paste,
                "_set_clipboard_text",
                side_effect=clipboard.ClipboardError("write failed"),
            ),
            patch.object(
                clipboard_paste.user32,
                "CloseClipboard",
            ),
        ):
            with self.assertRaisesRegex(
                clipboard.ClipboardError,
                "write failed",
            ):
                clipboard_paste._replace_clipboard("snippet", b"marker")

        self.assertEqual(snapshot.restore_calls, 1)

    def test_replacement_and_snapshot_restore_failures_are_both_preserved(self):
        operation_error = clipboard.ClipboardError("write failed")
        restore_error = clipboard.ClipboardError("snapshot restore failed")
        snapshot = Mock()
        snapshot.restore.side_effect = restore_error
        with (
            patch.object(
                clipboard_paste.ClipboardSnapshot,
                "capture",
                return_value=snapshot,
            ),
            patch.object(clipboard_paste, "_open_clipboard"),
            patch.object(
                clipboard_paste.user32,
                "EmptyClipboard",
                return_value=True,
            ),
            patch.object(
                clipboard_paste,
                "_set_clipboard_text",
                side_effect=operation_error,
            ),
            patch.object(clipboard_paste.user32, "CloseClipboard"),
        ):
            with self.assertRaises(ClipboardRestoreError) as raised:
                clipboard_paste._replace_clipboard("snippet", b"marker")

        self.assertIs(raised.exception.operation_error, operation_error)
        self.assertIs(raised.exception.restore_error, restore_error)
        self.assertIs(raised.exception.__cause__, operation_error)


if __name__ == "__main__":
    unittest.main()
