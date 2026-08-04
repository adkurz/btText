import unittest
from unittest.mock import Mock, patch

from platform_support import clipboard, clipboard_snapshot
from platform_support.clipboard_snapshot import (
    ClipboardSnapshot,
    _ClipboardFormatCopy,
)


class ClipboardSnapshotTestCase(unittest.TestCase):
    def test_empty_clipboard_creates_empty_snapshot(self):
        with (
            patch.object(clipboard_snapshot, "_open_clipboard"),
            patch.object(
                clipboard_snapshot.user32,
                "EnumClipboardFormats",
                return_value=0,
            ),
            patch.object(clipboard_snapshot.user32, "CloseClipboard"),
        ):
            snapshot = ClipboardSnapshot.capture()

        self.assertEqual(snapshot._copied_formats, [])

    def test_capture_retries_a_temporarily_unavailable_format(self):
        copied_format = Mock()
        format_error = clipboard_snapshot._ClipboardFormatError(
            2,
            "format unavailable",
            clipboard_snapshot.ERROR_CLIPBOARD_FORMAT_NOT_AVAILABLE,
        )
        with (
            patch.object(
                clipboard_snapshot,
                "_copy_clipboard_formats",
                side_effect=(format_error, [copied_format]),
            ) as copy_formats,
            patch.object(clipboard_snapshot.time, "sleep") as sleep,
        ):
            snapshot = ClipboardSnapshot.capture()

        self.assertEqual(snapshot._copied_formats, [copied_format])
        self.assertEqual(copy_formats.call_count, 2)
        sleep.assert_called_once_with(clipboard_snapshot.CAPTURE_RETRY_DELAY)

    def test_capture_degrades_after_repeated_format_failure(self):
        copied_format = Mock()
        format_error = clipboard_snapshot._ClipboardFormatError(
            49152,
            "format unavailable",
            clipboard_snapshot.ERROR_CLIPBOARD_FORMAT_NOT_AVAILABLE,
        )
        with (
            patch.object(
                clipboard_snapshot,
                "_copy_clipboard_formats",
                side_effect=(
                    format_error,
                    format_error,
                    format_error,
                    [copied_format],
                ),
            ) as copy_formats,
            patch.object(clipboard_snapshot.time, "sleep"),
        ):
            snapshot = ClipboardSnapshot.capture()

        self.assertEqual(snapshot._copied_formats, [copied_format])
        self.assertEqual(
            copy_formats.call_args_list[-1].kwargs,
            {"skip_unavailable": True},
        )

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

    def test_enumeration_failure_is_not_treated_as_empty_clipboard(self):
        with (
            patch.object(clipboard_snapshot, "_open_clipboard"),
            patch.object(
                clipboard_snapshot.user32,
                "EnumClipboardFormats",
                return_value=0,
            ),
            patch.object(
                clipboard_snapshot.ctypes,
                "get_last_error",
                return_value=5,
            ),
            patch.object(clipboard_snapshot.user32, "CloseClipboard"),
        ):
            with self.assertRaisesRegex(
                clipboard.ClipboardError,
                "Windows error 5",
            ):
                clipboard_snapshot._copy_clipboard_formats()

    def test_diagnostic_format_name_replaces_control_characters(self):
        buffer_value = "Unsafe\nFormat"

        def set_format_name(_format_id, buffer, _length):
            buffer.value = buffer_value
            return len(buffer_value)

        with patch.object(
            clipboard_snapshot.user32,
            "GetClipboardFormatNameW",
            side_effect=set_format_name,
        ):
            name = clipboard_snapshot._clipboard_format_name(49152)

        self.assertEqual(name, "Unsafe?Format")

    def test_degraded_capture_skips_one_unavailable_format_and_logs_metadata(self):
        copied_format = Mock()
        format_error = clipboard_snapshot._ClipboardFormatError(
            2,
            "format unavailable",
            clipboard_snapshot.ERROR_CLIPBOARD_FORMAT_NOT_AVAILABLE,
        )
        with (
            patch.object(clipboard_snapshot, "_open_clipboard"),
            patch.object(
                clipboard_snapshot.user32,
                "EnumClipboardFormats",
                side_effect=(1, 2, 0),
            ),
            patch.object(
                clipboard_snapshot,
                "_copy_clipboard_format",
                side_effect=(copied_format, format_error),
            ),
            patch.object(
                clipboard_snapshot,
                "_clipboard_format_name",
                return_value="DelayedFormat",
            ),
            patch.object(clipboard_snapshot.user32, "CloseClipboard"),
            self.assertLogs("bttext.clipboard", level="WARNING") as logs,
        ):
            result = clipboard_snapshot._copy_clipboard_formats(
                skip_unavailable=True
            )

        self.assertEqual(result, [copied_format])
        self.assertIn(
            "id=2 name=DelayedFormat windows_error=1418",
            logs.output[0],
        )

    def test_degraded_capture_does_not_replace_only_unavailable_content(self):
        format_error = clipboard_snapshot._ClipboardFormatError(
            49152,
            "format unavailable",
            clipboard_snapshot.ERROR_CLIPBOARD_FORMAT_NOT_AVAILABLE,
        )
        with (
            patch.object(clipboard_snapshot, "_open_clipboard"),
            patch.object(
                clipboard_snapshot.user32,
                "EnumClipboardFormats",
                side_effect=(1, 0),
            ),
            patch.object(
                clipboard_snapshot,
                "_copy_clipboard_format",
                side_effect=format_error,
            ),
            patch.object(
                clipboard_snapshot,
                "_clipboard_format_name",
                return_value="DelayedFormat",
            ),
            patch.object(clipboard_snapshot.user32, "CloseClipboard"),
            self.assertLogs("bttext.clipboard", level="WARNING"),
        ):
            with self.assertRaisesRegex(
                clipboard.ClipboardError,
                "copy plain text or clear the clipboard",
            ):
                clipboard_snapshot._copy_clipboard_formats(
                    skip_unavailable=True
                )

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
