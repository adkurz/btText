import unittest
from unittest.mock import patch

from core.rich_text import ClipboardContent
from platform_support import clipboard


class CopyTextTestCase(unittest.TestCase):
    def setUp(self):
        self.owner_window = self.enterContext(
            patch.object(clipboard.user32, "CreateWindowExW", return_value=123)
        )
        self.enterContext(patch.object(clipboard.user32, "DestroyWindow", return_value=True))

    def test_privacy_controls_protect_content_even_when_a_format_write_fails(self):
        content = ClipboardContent("Private", "<p>Private</p>", rtf=b"{\\rtf1 Private}")
        content_formats = (
            clipboard.CF_UNICODETEXT,
            clipboard._HTML_FORMAT,
            clipboard._RTF_FORMAT,
        )
        for include_in_history, allow_cloud_upload in (
            (True, True), (False, True), (True, False), (False, False),
        ):
            for failed_format in (None, *content_formats):
                with self.subTest(
                    history=include_in_history,
                    cloud=allow_cloud_upload,
                    failed_format=failed_format,
                ):
                    published = {}
                    exclusions = {
                        clipboard._CLIPBOARD_HISTORY_FORMAT: not include_in_history,
                        clipboard._CLOUD_CLIPBOARD_FORMAT: not allow_cloud_upload,
                    }

                    def set_data(format_id, data):
                        if format_id in content_formats:
                            for privacy_format, excluded in exclusions.items():
                                if excluded:
                                    self.assertEqual(
                                        published.get(privacy_format), b"\0" * 4,
                                    )
                                else:
                                    self.assertNotIn(privacy_format, published)
                        if format_id == failed_format:
                            raise clipboard.ClipboardError("format write failed")
                        published[format_id] = data

                    with (
                        patch.object(clipboard, "_open_clipboard"),
                        patch.object(clipboard.user32, "EmptyClipboard", return_value=True),
                        patch.object(clipboard, "_set_clipboard_data", side_effect=set_data),
                        patch.object(clipboard.user32, "CloseClipboard") as close_clipboard,
                    ):
                        if failed_format is None:
                            clipboard.copy_content(
                                content, include_in_history, allow_cloud_upload,
                            )
                        else:
                            with self.assertRaisesRegex(
                                clipboard.ClipboardError, "format write failed",
                            ):
                                clipboard.copy_content(
                                    content, include_in_history, allow_cloud_upload,
                                )

                    close_clipboard.assert_called_once_with()
                    successful_formats = (
                        content_formats[:content_formats.index(failed_format)]
                        if failed_format is not None else content_formats
                    )
                    self.assertEqual(
                        set(published),
                        set(successful_formats) | {
                            format_id for format_id, excluded in exclusions.items() if excluded
                        },
                    )

    def test_failed_privacy_control_prevents_all_content_publication(self):
        privacy_formats = (
            clipboard._CLIPBOARD_HISTORY_FORMAT,
            clipboard._CLOUD_CLIPBOARD_FORMAT,
        )
        for failed_format in privacy_formats:
            with self.subTest(failed_format=failed_format):
                attempted_formats = []

                def set_data(format_id, data):
                    attempted_formats.append(format_id)
                    if format_id == failed_format:
                        raise clipboard.ClipboardError("privacy write failed")

                with (
                    patch.object(clipboard, "_open_clipboard"),
                    patch.object(clipboard.user32, "EmptyClipboard", return_value=True),
                    patch.object(clipboard, "_set_clipboard_data", side_effect=set_data),
                    patch.object(clipboard.user32, "CloseClipboard") as close_clipboard,
                ):
                    with self.assertRaisesRegex(
                        clipboard.ClipboardError, "privacy write failed",
                    ):
                        clipboard.copy_content(
                            ClipboardContent(
                                "Private", "<p>Private</p>", rtf=b"{\\rtf1 Private}",
                            ),
                            include_in_history=False,
                            allow_cloud_upload=False,
                        )

                self.assertEqual(
                    attempted_formats,
                    list(privacy_formats[:privacy_formats.index(failed_format) + 1]),
                )
                close_clipboard.assert_called_once_with()

    def test_copy_content_sets_plain_text_and_html(self):
        content = ClipboardContent(
            "Hello",
            "<p><strong>Hello</strong></p>",
            rtf=b"{\\rtf1 Hello}",
        )
        with (
            patch.object(clipboard, "_open_clipboard"),
            patch.object(clipboard.user32, "EmptyClipboard", return_value=True),
            patch.object(clipboard, "_set_clipboard_text") as set_text,
            patch.object(clipboard, "_set_clipboard_data") as set_data,
            patch.object(clipboard.user32, "CloseClipboard"),
        ):
            clipboard.copy_content(content)

        set_text.assert_called_once_with("Hello")
        html_call = next(
            call for call in set_data.call_args_list
            if call.args[0] == clipboard._HTML_FORMAT
        )
        self.assertIn(b"<strong>Hello</strong>", html_call.args[1])
        set_data.assert_any_call(
            clipboard._RTF_FORMAT,
            b"{\\rtf1 Hello}\0",
        )

    def test_cf_html_offsets_address_utf8_bytes(self):
        encoded = clipboard._encode_cf_html("<p>Gr\N{LATIN SMALL LETTER U WITH DIAERESIS}\N{WHITE SMILING FACE}</p>")
        payload = encoded.rstrip(b"\0")
        header, _html = payload.split(b"<html>", 1)
        offsets = {}
        for line in header.decode("ascii").splitlines():
            key, value = line.split(":", 1)
            if key != "Version":
                offsets[key] = int(value)

        self.assertEqual(payload[offsets["StartHTML"] : offsets["StartHTML"] + 6], b"<html>")
        self.assertEqual(
            payload[offsets["StartFragment"] : offsets["EndFragment"]],
            "<p>Gr\N{LATIN SMALL LETTER U WITH DIAERESIS}\N{WHITE SMILING FACE}</p>".encode("utf-8"),
        )
        self.assertEqual(offsets["EndHTML"], len(payload))

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

        open_clipboard.assert_called_once_with(owner=123)
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
