import unittest
from unittest.mock import patch

from platform_support import clipboard


class CopyTextTestCase(unittest.TestCase):
    def test_copy_text_replaces_clipboard_with_unicode_text(self):
        with (
            patch.object(clipboard, "_open_clipboard") as open_clipboard,
            patch.object(
                clipboard.user32,
                "EmptyClipboard",
                return_value=True,
            ) as empty_clipboard,
            patch.object(clipboard, "_set_clipboard_text") as set_text,
            patch.object(
                clipboard.user32,
                "CloseClipboard",
            ) as close_clipboard,
        ):
            clipboard.copy_text("Text \N{CHECK MARK}")

        open_clipboard.assert_called_once_with()
        empty_clipboard.assert_called_once_with()
        set_text.assert_called_once_with("Text \N{CHECK MARK}")
        close_clipboard.assert_called_once_with()

    def test_copy_text_closes_clipboard_when_clearing_fails(self):
        with (
            patch.object(clipboard, "_open_clipboard"),
            patch.object(
                clipboard.user32,
                "EmptyClipboard",
                return_value=False,
            ),
            patch.object(
                clipboard.user32,
                "CloseClipboard",
            ) as close_clipboard,
        ):
            with self.assertRaises(clipboard.ClipboardError):
                clipboard.copy_text("Text")

        close_clipboard.assert_called_once_with()

    def test_copy_text_can_be_excluded_from_clipboard_history(self):
        with (
            patch.object(clipboard, "_open_clipboard"),
            patch.object(
                clipboard.user32,
                "EmptyClipboard",
                return_value=True,
            ),
            patch.object(clipboard, "_set_clipboard_text"),
            patch.object(
                clipboard,
                "_set_clipboard_data",
            ) as set_clipboard_data,
            patch.object(clipboard.user32, "CloseClipboard"),
        ):
            clipboard.copy_text("Private", include_in_history=False)

        set_clipboard_data.assert_called_once_with(
            clipboard._CLIPBOARD_HISTORY_FORMAT,
            b"\0\0\0\0",
        )

    def test_copy_text_can_be_excluded_from_cloud_clipboard(self):
        with (
            patch.object(clipboard, "_open_clipboard"),
            patch.object(
                clipboard.user32,
                "EmptyClipboard",
                return_value=True,
            ),
            patch.object(clipboard, "_set_clipboard_text"),
            patch.object(
                clipboard,
                "_set_clipboard_data",
            ) as set_clipboard_data,
            patch.object(clipboard.user32, "CloseClipboard"),
        ):
            clipboard.copy_text("Private", allow_cloud_upload=False)

        set_clipboard_data.assert_called_once_with(
            clipboard._CLOUD_CLIPBOARD_FORMAT,
            b"\0\0\0\0",
        )


class ReadTextTestCase(unittest.TestCase):
    def test_read_text_opens_and_closes_clipboard(self):
        with (
            patch.object(clipboard, "_open_clipboard") as open_clipboard,
            patch.object(
                clipboard,
                "_read_open_clipboard_text",
                return_value="Copied text",
            ),
            patch.object(
                clipboard.user32,
                "CloseClipboard",
            ) as close_clipboard,
        ):
            result = clipboard.read_text()

        self.assertEqual(result, "Copied text")
        open_clipboard.assert_called_once_with()
        close_clipboard.assert_called_once_with()

    def test_read_text_closes_clipboard_after_failure(self):
        with (
            patch.object(clipboard, "_open_clipboard"),
            patch.object(
                clipboard,
                "_read_open_clipboard_text",
                side_effect=clipboard.ClipboardError("unavailable"),
            ),
            patch.object(
                clipboard.user32,
                "CloseClipboard",
            ) as close_clipboard,
        ):
            with self.assertRaises(clipboard.ClipboardError):
                clipboard.read_text()

        close_clipboard.assert_called_once_with()

    def test_open_clipboard_without_unicode_text_returns_none(self):
        with patch.object(
            clipboard.user32,
            "IsClipboardFormatAvailable",
            return_value=False,
        ):
            self.assertIsNone(clipboard._read_open_clipboard_text())

    def test_open_clipboard_reads_unicode_text_without_modifying_it(self):
        encoded = "Text \N{CHECK MARK}\0".encode("utf-16-le")
        with (
            patch.object(
                clipboard.user32,
                "IsClipboardFormatAvailable",
                return_value=True,
            ),
            patch.object(
                clipboard.user32,
                "GetClipboardData",
                return_value=123,
            ),
            patch.object(
                clipboard.kernel32,
                "GlobalLock",
                return_value=456,
            ),
            patch.object(
                clipboard.kernel32,
                "GlobalSize",
                return_value=len(encoded),
            ),
            patch.object(clipboard.ctypes, "string_at", return_value=encoded),
            patch.object(
                clipboard.kernel32,
                "GlobalUnlock",
            ) as global_unlock,
        ):
            result = clipboard._read_open_clipboard_text()

        self.assertEqual(result, "Text \N{CHECK MARK}")
        global_unlock.assert_called_once_with(123)
