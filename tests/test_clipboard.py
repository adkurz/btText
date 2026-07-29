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
