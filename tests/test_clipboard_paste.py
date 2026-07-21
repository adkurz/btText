import unittest
from unittest.mock import Mock, patch

import clipboard_paste
from clipboard_paste import PendingPaste, _ClipboardSnapshot


class RecordingClipboardSnapshot:
    def __init__(self):
        self.close_calls = 0
        self.restore_calls = 0

    def close(self):
        self.close_calls += 1

    def restore(self):
        self.restore_calls += 1


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


class ClipboardSnapshotTestCase(unittest.TestCase):
    def test_restore_uses_independent_copies_for_normal_text(self):
        copied_formats = [
            (clipboard_paste.CF_UNICODETEXT, "original\0".encode("utf-16-le"))
        ]
        snapshot = _ClipboardSnapshot(object(), copied_formats)
        snapshot.close = Mock()

        with patch.object(
            clipboard_paste,
            "_restore_copied_formats",
        ) as restore_copied_formats:
            snapshot.restore()

        restore_copied_formats.assert_called_once_with(copied_formats)
        snapshot.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
