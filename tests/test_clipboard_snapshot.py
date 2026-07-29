import unittest
from unittest.mock import Mock, patch

from platform_support import clipboard, clipboard_snapshot
from platform_support.clipboard_snapshot import (
    ClipboardSnapshot,
    _ClipboardFormatCopy,
)


class ClipboardSnapshotTestCase(unittest.TestCase):
    def test_restore_uses_independent_copies_for_normal_text(self):
        copied_formats = [
            _ClipboardFormatCopy(
                clipboard.CF_UNICODETEXT,
                "hglobal",
                "original\0".encode("utf-16-le"),
            )
        ]
        snapshot = ClipboardSnapshot(copied_formats)
        snapshot.close = Mock()

        with patch.object(
            clipboard_snapshot,
            "_restore_copied_formats",
        ) as restore_copied_formats:
            snapshot.restore()

        restore_copied_formats.assert_called_once_with(copied_formats)
        snapshot.close.assert_called_once_with()

    def test_discard_releases_copied_bitmap(self):
        copied_format = _ClipboardFormatCopy(
            clipboard_snapshot.CF_BITMAP,
            "bitmap",
            123,
        )
        snapshot = ClipboardSnapshot([copied_format])

        with patch.object(clipboard_snapshot.gdi32, "DeleteObject") as delete:
            snapshot.close()

        delete.assert_called_once_with(123)

    def test_successful_restore_transfers_bitmap_ownership(self):
        copied_format = _ClipboardFormatCopy(
            clipboard_snapshot.CF_BITMAP,
            "bitmap",
            123,
        )

        with (
            patch.object(clipboard_snapshot, "_open_clipboard"),
            patch.object(
                clipboard_snapshot.user32,
                "EmptyClipboard",
                return_value=True,
            ),
            patch.object(
                clipboard_snapshot.user32,
                "SetClipboardData",
                return_value=123,
            ),
            patch.object(clipboard_snapshot.user32, "CloseClipboard"),
            patch.object(clipboard_snapshot.gdi32, "DeleteObject") as delete,
        ):
            clipboard_snapshot._restore_copied_formats([copied_format])
            copied_format.release()

        delete.assert_not_called()

    def test_failed_restore_keeps_bitmap_ownership_for_release(self):
        copied_format = _ClipboardFormatCopy(
            clipboard_snapshot.CF_BITMAP,
            "bitmap",
            123,
        )

        with (
            patch.object(clipboard_snapshot, "_open_clipboard"),
            patch.object(
                clipboard_snapshot.user32,
                "EmptyClipboard",
                return_value=True,
            ),
            patch.object(
                clipboard_snapshot.user32,
                "SetClipboardData",
                return_value=None,
            ),
            patch.object(clipboard_snapshot.user32, "CloseClipboard"),
            patch.object(clipboard_snapshot.gdi32, "DeleteObject") as delete,
        ):
            with self.assertRaises(clipboard.ClipboardError):
                clipboard_snapshot._restore_copied_formats([copied_format])
            copied_format.release()

        delete.assert_called_once_with(123)

    def test_capture_error_releases_formats_copied_so_far(self):
        copied_format = Mock()

        with (
            patch.object(clipboard_snapshot, "_open_clipboard"),
            patch.object(
                clipboard_snapshot.user32,
                "EnumClipboardFormats",
                side_effect=(1, 2),
            ),
            patch.object(
                clipboard_snapshot,
                "_copy_clipboard_format",
                side_effect=(
                    copied_format,
                    clipboard.ClipboardError("copy failed"),
                ),
            ),
            patch.object(
                clipboard_snapshot.user32,
                "CloseClipboard",
            ) as close_clipboard,
        ):
            with self.assertRaisesRegex(
                clipboard.ClipboardError,
                "copy failed",
            ):
                clipboard_snapshot._copy_clipboard_formats()

        copied_format.release.assert_called_once_with()
        close_clipboard.assert_called_once_with()

    def test_owner_display_has_no_transferable_data(self):
        with patch.object(
            clipboard_snapshot.user32,
            "GetClipboardData",
            return_value=None,
        ):
            copied_format = clipboard_snapshot._copy_clipboard_format(
                clipboard_snapshot.CF_OWNERDISPLAY
            )

        self.assertIsNone(copied_format)
