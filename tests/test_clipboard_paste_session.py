"""Regression coverage for overlapping manual and hotstring paste operations."""

import unittest
from unittest.mock import Mock, patch

from core.app_settings import AppSettings
from core.datamodel import Snippet
from core.rich_text import ClipboardContent
from core.variables import RenderedSnippet
from platform_support import clipboard, clipboard_paste, clipboard_snapshot
from platform_support import hotstring_expansion, hotstrings
from platform_support.clipboard_paste import ClipboardPasteSession
from platform_support.clipboard_snapshot import ClipboardSnapshot, _ClipboardFormatCopy
from platform_support.windows import WindowIdentity
from ui.hotstring_controller import HotstringController
from ui.paste_controller import PasteController


TARGET = WindowIdentity(handle=123, thread_id=7, process_id=9)


class ClipboardPasteSessionTestCase(unittest.TestCase):
    def setUp(self):
        self.original = {
            clipboard.CF_UNICODETEXT: "original\0".encode("utf-16-le"),
            clipboard._HTML_FORMAT: b"original HTML\0",
            clipboard._RTF_FORMAT: b"original RTF\0",
        }
        self.formats = dict(self.original)
        self.locked = False
        self.sequence = 100
        self.fail_next_write = False
        self.fail_next_open = False
        self.fail_open = False
        self.session = ClipboardPasteSession()
        self.enterContext(patch.object(clipboard.user32, "CreateWindowExW", return_value=123))
        self.enterContext(patch.object(clipboard.user32, "DestroyWindow", return_value=True))
        self.enterContext(patch.object(clipboard.user32, "CloseClipboard", side_effect=self._close))
        self.enterContext(patch.object(clipboard.user32, "EmptyClipboard", side_effect=self._empty))
        self.enterContext(patch.object(clipboard.user32, "GetClipboardSequenceNumber", side_effect=self._sequence))
        self.enterContext(patch.object(clipboard_paste, "_open_clipboard", side_effect=self._open))
        self.enterContext(patch.object(clipboard_snapshot, "_open_clipboard", side_effect=self._open))
        self.enterContext(patch.object(clipboard_snapshot, "_copy_open_clipboard_formats", side_effect=self._capture))
        self.enterContext(patch.object(clipboard, "_set_clipboard_data", side_effect=self._write))
        self.enterContext(patch.object(clipboard_paste, "_set_clipboard_data", side_effect=self._write))
        self.enterContext(patch.object(clipboard_snapshot, "_set_clipboard_data", side_effect=self._write))
        self.enterContext(patch.object(clipboard_paste, "_read_clipboard_bytes", side_effect=self._read))
        self.enterContext(patch.object(clipboard_paste.windows, "matches_window_identity", return_value=True))
        self.enterContext(patch.object(clipboard_paste.windows, "activate_window_identity", return_value=True))
        self.enterContext(patch.object(clipboard_paste.keyboard_input, "send_ctrl_v"))
        self.enterContext(patch.object(hotstring_expansion.keyboard_input, "send_hotstring_replacement"))

    def _open(self, *, owner=None):
        self.assertFalse(self.locked)
        if self.fail_open or self.fail_next_open:
            self.fail_next_open = False
            raise clipboard.ClipboardError("clipboard busy")
        self.locked = True

    def _close(self):
        self.assertTrue(self.locked)
        self.locked = False

    def _sequence(self):
        self.assertTrue(self.locked)
        return self.sequence

    def _empty(self):
        self.assertTrue(self.locked)
        self.formats.clear()
        self.sequence += 1
        return True

    def _write(self, format_id, data):
        self.assertTrue(self.locked)
        if self.fail_next_write:
            self.fail_next_write = False
            raise clipboard.ClipboardError("write failed")
        self.formats[format_id] = data
        self.sequence += 1

    def _read(self, format_id):
        self.assertTrue(self.locked)
        return self.formats.get(format_id)

    def _capture(self):
        self.assertTrue(self.locked)
        return [
            _ClipboardFormatCopy(format_id, "hglobal", data)
            for format_id, data in self.formats.items()
        ]

    def _paste(self, kind, text):
        content = ClipboardContent(text, f"<p>{text}</p>", rtf=b"{\\rtf1 snippet}")
        if kind == "manual":
            pending = clipboard_paste.paste_text(TARGET, content, session=self.session)
        else:
            pending = hotstring_expansion.expand_hotstring(
                TARGET, content, 3, 32, session=self.session
            )
        self.addCleanup(pending.discard_snapshot)
        return pending

    def test_overlapping_pastes_restore_all_original_formats_in_either_timer_order(self):
        for first_kind, second_kind in (
            ("manual", "manual"),
            ("hotstring", "hotstring"),
            ("manual", "hotstring"),
            ("hotstring", "manual"),
        ):
            for newest_timer_first in (False, True):
                with self.subTest(kinds=(first_kind, second_kind), newest_first=newest_timer_first):
                    first = self._paste(first_kind, "snippet A")
                    second = self._paste(second_kind, "snippet B")
                    latest = dict(self.formats)
                    if newest_timer_first:
                        second.restore_clipboard()
                        first.restore_clipboard()
                    else:
                        first.restore_clipboard()
                        self.assertEqual(self.formats, latest)
                        second.restore_clipboard()
                    self.assertEqual(self.formats, self.original)
                    self.assertTrue(first._snapshot._closed)
                    self.assertTrue(second._snapshot._closed)

    def test_three_overlapping_pastes_leave_only_latest_restore_active(self):
        first = self._paste("manual", "snippet A")
        second = self._paste("hotstring", "snippet B")
        third = self._paste("manual", "snippet C")
        latest = dict(self.formats)

        second.restore_clipboard()
        first.restore_clipboard()
        self.assertEqual(self.formats, latest)
        third.restore_clipboard()

        self.assertEqual(self.formats, self.original)

    def test_external_copy_between_pastes_becomes_the_new_restore_baseline(self):
        first = self._paste("manual", "snippet A")
        # Identical text with a missing marker is still a new user-owned copy.
        external = {
            clipboard.CF_UNICODETEXT: "snippet A\0".encode("utf-16-le"),
            clipboard._HTML_FORMAT: b"new user HTML\0",
        }
        self.formats = dict(external)
        self.sequence += 1
        second = self._paste("hotstring", "snippet B")

        first.restore_clipboard()
        second.restore_clipboard()

        self.assertEqual(self.formats, external)

    def test_new_external_copy_after_latest_paste_survives_all_old_timers(self):
        first = self._paste("hotstring", "snippet A")
        second = self._paste("manual", "snippet B")
        external = {clipboard.CF_UNICODETEXT: "user copy\0".encode("utf-16-le")}
        self.formats = dict(external)
        self.sequence += 1

        second.restore_clipboard()
        first.restore_clipboard()

        self.assertEqual(self.formats, external)

    def test_failed_prior_restore_rejects_next_paste_and_remains_retryable(self):
        first = self._paste("manual", "snippet A")
        self.fail_next_write = True
        with patch.object(ClipboardSnapshot, "capture", wraps=ClipboardSnapshot.capture) as capture:
            with self.assertRaisesRegex(clipboard.ClipboardError, "write failed"):
                self._paste("hotstring", "snippet B")
            capture.assert_not_called()
        self.assertFalse(first._snapshot._closed)

        first.restore_clipboard()
        self.assertEqual(self.formats, self.original)
        second = self._paste("hotstring", "snippet B")
        first.restore_clipboard()
        second.restore_clipboard()
        self.assertEqual(self.formats, self.original)

    def test_failed_second_activation_restores_original_instead_of_first_snippet(self):
        first = self._paste("manual", "snippet A")
        with patch.object(clipboard_paste.windows, "activate_window_identity", return_value=False):
            with self.assertRaises(clipboard_paste.PasteTargetError):
                self._paste("manual", "snippet B")

        first.restore_clipboard()

        self.assertEqual(self.formats, self.original)

    def _failed_controller_paste(self, kind, *, operation="activation", recovery="open"):
        """Inject failure after preparation and retain actual scheduled callbacks."""
        timers = []
        errors = Mock()
        paste_controller = PasteController.__new__(PasteController)
        paste_controller._clipboard_session = self.session
        paste_controller._reveal_after_error = errors

        def fail_operation(*_arguments):
            self.fail_next_open = recovery == "open"
            self.fail_open = recovery == "permanent_open"
            self.fail_next_write = recovery == "write"
            if operation == "activation":
                return False
            raise clipboard.ClipboardError("keyboard input failed")

        with (
            patch("ui.paste_controller.wx.CallLater", side_effect=lambda delay, callback, *args:
                  timers.append((delay, callback, args))),
            patch.object(clipboard_paste.windows, "activate_window_identity",
                         side_effect=fail_operation if operation == "activation" else None,
                         return_value=True),
            patch.object(clipboard_paste.keyboard_input, "send_ctrl_v",
                         side_effect=fail_operation if operation == "input" else None),
            patch.object(hotstring_expansion.keyboard_input, "send_hotstring_replacement",
                         side_effect=fail_operation if operation == "input" else None),
            patch("ui.hotstring_controller.hotstrings.KeyboardHook"),
        ):
            if kind == "manual":
                paste_controller._paste_after_hide(TARGET, ClipboardContent("snippet"))
            else:
                controller = HotstringController(
                    Mock(), Mock(), Mock(), lambda: AppSettings(),
                    paste_controller.schedule_restore, Mock(),
                    lambda *args: RenderedSnippet("snippet"),
                    clipboard_session=self.session,
                )
                controller._show_hotstring_error = errors
                controller._expand(
                    TARGET, Snippet("Test", "snippet", 1, hotstring="test"),
                    32, hotstrings.InputCheckpoint((123, 124, 125)),
                )
        errors.assert_called_once()
        return timers, errors

    def test_failed_recovery_automatically_restores_original_formats(self):
        for kind in ("manual", "hotstring"):
            for operation in ("activation", "input"):
                for recovery in ("open", "write"):
                    with self.subTest(kind=kind, operation=operation, recovery=recovery):
                        timers, _errors = self._failed_controller_paste(
                            kind, operation=operation, recovery=recovery,
                        )
                        self.assertEqual(len(timers), 1)
                        delay, callback, arguments = timers.pop()
                        self.assertEqual(delay, 500)
                        pending, attempts = arguments
                        self.assertEqual(attempts, 3)
                        self.assertFalse(pending._snapshot._closed)
                        callback(*arguments)
                        self.assertEqual(self.formats, self.original)
                        self.assertTrue(pending._snapshot._closed)

    def test_failed_recovery_preserves_new_external_copy_on_retry(self):
        for kind in ("manual", "hotstring"):
            with self.subTest(kind=kind):
                timers, _errors = self._failed_controller_paste(kind)
                self.assertEqual(len(timers), 1)
                external = {
                    clipboard.CF_UNICODETEXT: "snippet\0".encode("utf-16-le"),
                    clipboard._HTML_FORMAT: b"new user HTML\0",
                }
                self.formats = dict(external)
                self.sequence += 1
                _delay, callback, arguments = timers.pop()
                callback(*arguments)
                self.assertEqual(self.formats, external)
                self.assertTrue(arguments[0]._snapshot._closed)
                self.formats = dict(self.original)

    def test_failed_recovery_stops_after_bounded_retries(self):
        for kind in ("manual", "hotstring"):
            with self.subTest(kind=kind):
                timers, errors = self._failed_controller_paste(kind, recovery="permanent_open")
                self.assertEqual(len(timers), 1)
                pending = timers[0][2][0]
                attempts = []
                delays = []
                with patch("ui.paste_controller.wx.CallLater", side_effect=lambda delay, callback, *args:
                           timers.append((delay, callback, args))):
                    while timers:
                        delay, callback, arguments = timers.pop(0)
                        attempts.append(arguments[1])
                        delays.append(delay)
                        callback(*arguments)
                self.assertEqual(attempts, [3, 2, 1])
                self.assertEqual(delays, [500, 100, 100])
                self.assertTrue(pending._snapshot._closed)
                self.assertEqual(errors.call_count, 2)
                self.fail_open = False
                self.formats = dict(self.original)

    def test_failed_recovery_timer_cannot_overwrite_a_new_paste(self):
        for kind in ("manual", "hotstring"):
            with self.subTest(kind=kind):
                timers, _errors = self._failed_controller_paste(kind)
                self.assertEqual(len(timers), 1)
                latest = self._paste("hotstring" if kind == "manual" else "manual", "next snippet")
                expected = dict(self.formats)
                _delay, callback, arguments = timers.pop()
                callback(*arguments)
                self.assertEqual(self.formats, expected)
                latest.restore_clipboard()
                self.assertEqual(self.formats, self.original)

    def test_successful_immediate_recovery_does_not_schedule_retry(self):
        for kind in ("manual", "hotstring"):
            with self.subTest(kind=kind):
                timers, _errors = self._failed_controller_paste(kind, recovery=None)
                self.assertEqual(timers, [])
                self.assertEqual(self.formats, self.original)


if __name__ == "__main__":
    unittest.main()
