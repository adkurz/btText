import unittest
from unittest.mock import Mock, patch

from platform_support import clipboard, clipboard_paste
from platform_support.clipboard_paste import (
    PendingPaste,
    _ClipboardFormatCopy,
    _ClipboardSnapshot,
)


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


class ClipboardSnapshotTestCase(unittest.TestCase):
    def test_restore_uses_independent_copies_for_normal_text(self):
        copied_formats = [
            _ClipboardFormatCopy(
                clipboard_paste.CF_UNICODETEXT,
                "hglobal",
                "original\0".encode("utf-16-le"),
            )
        ]
        snapshot = _ClipboardSnapshot(copied_formats)
        snapshot.close = Mock()

        with patch.object(
            clipboard_paste,
            "_restore_copied_formats",
        ) as restore_copied_formats:
            snapshot.restore()

        restore_copied_formats.assert_called_once_with(copied_formats)
        snapshot.close.assert_called_once_with()

    def test_discard_releases_copied_bitmap(self):
        copied_format = _ClipboardFormatCopy(
            clipboard_paste.CF_BITMAP, "bitmap", 123
        )
        snapshot = _ClipboardSnapshot([copied_format])

        with patch.object(clipboard_paste.gdi32, "DeleteObject") as delete:
            snapshot.close()

        delete.assert_called_once_with(123)

    def test_successful_restore_transfers_bitmap_ownership(self):
        copied_format = _ClipboardFormatCopy(
            clipboard_paste.CF_BITMAP, "bitmap", 123
        )

        with (
            patch.object(clipboard_paste, "_open_clipboard"),
            patch.object(clipboard_paste.user32, "EmptyClipboard", return_value=True),
            patch.object(clipboard_paste.user32, "SetClipboardData", return_value=123),
            patch.object(clipboard_paste.user32, "CloseClipboard"),
            patch.object(clipboard_paste.gdi32, "DeleteObject") as delete,
        ):
            clipboard_paste._restore_copied_formats([copied_format])
            copied_format.release()

        delete.assert_not_called()

    def test_owner_display_has_no_transferable_data(self):
        with patch.object(
            clipboard_paste.user32, "GetClipboardData", return_value=None
        ):
            copied_format = clipboard_paste._copy_clipboard_format(
                clipboard_paste.CF_OWNERDISPLAY
            )

        self.assertIsNone(copied_format)


class HotstringExpansionTestCase(unittest.TestCase):
    def _expand(self, boundary_key):
        snapshot = RecordingClipboardSnapshot()
        with (
            patch.object(
                clipboard_paste.user32, "IsWindow", return_value=True
            ),
            patch.object(
                clipboard_paste, "_replace_clipboard", return_value=snapshot
            ),
            patch.object(
                clipboard_paste, "activate_window", return_value=True
            ),
            patch.object(clipboard_paste, "_send_ctrl_v") as send_ctrl_v,
            patch.object(
                clipboard_paste, "_send_virtual_key"
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
