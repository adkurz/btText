import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

from platform_support import clipboard, clipboard_paste, clipboard_snapshot, windows
from platform_support.clipboard_paste import ClipboardRestoreError, PendingPaste
from platform_support.clipboard_snapshot import ClipboardSnapshot, _ClipboardFormatCopy


TARGET = windows.WindowIdentity(handle=123, thread_id=7, process_id=9)


class RecordingClipboardSnapshot:
    def __init__(self):
        self.close_calls = 0
        self.restore_calls = 0

    def close(self):
        self.close_calls += 1

    def restore(self, *, is_owner=None):
        if is_owner is not None and not is_owner():
            self.close()
            return
        self.restore_calls += 1


class PendingPasteTestCase(unittest.TestCase):
    @contextmanager
    def _restore_retry_scenario(self, *, fail_writes=()):
        original_formats = {
            clipboard.CF_UNICODETEXT: "original\0".encode("utf-16-le"),
            clipboard._HTML_FORMAT: b"original HTML\0",
            clipboard._RTF_FORMAT: b"original RTF\0",
        }
        snapshot = ClipboardSnapshot([
            _ClipboardFormatCopy(format_id, "hglobal", data)
            for format_id, data in original_formats.items()
        ])
        pending = PendingPaste(snapshot, b"marker")
        state = {
            "locked": False,
            "formats": {clipboard_paste._MARKER_FORMAT: b"marker"},
            "sequence": 100,
            "sequence_available": True,
            "writes": 0,
            "empties": 0,
            "fail_empty": False,
        }

        def open_clipboard():
            self.assertFalse(state["locked"])
            state["locked"] = True

        def close_clipboard():
            self.assertTrue(state["locked"])
            state["locked"] = False

        def read_marker(format_id):
            self.assertTrue(state["locked"])
            return state["formats"].get(format_id)

        def get_sequence():
            self.assertTrue(state["locked"])
            return state["sequence"] if state["sequence_available"] else 0

        def empty_clipboard():
            self.assertTrue(state["locked"])
            if state["fail_empty"]:
                return False
            state["empties"] += 1
            state["sequence"] += 1
            state["formats"].clear()
            return True

        def set_data(format_id, data):
            self.assertTrue(state["locked"])
            state["writes"] += 1
            if state["writes"] in fail_writes:
                raise clipboard.ClipboardError("write failed")
            state["sequence"] += 1
            state["formats"][format_id] = data

        with (
            patch.object(clipboard_snapshot, "_open_clipboard", side_effect=open_clipboard),
            patch.object(clipboard_paste, "_read_clipboard_bytes", side_effect=read_marker),
            patch.object(clipboard_snapshot.user32, "GetClipboardSequenceNumber", side_effect=get_sequence),
            patch.object(clipboard_snapshot.user32, "EmptyClipboard", side_effect=empty_clipboard),
            patch.object(clipboard_snapshot, "_set_clipboard_data", side_effect=set_data),
            patch.object(clipboard_snapshot.user32, "CloseClipboard", side_effect=close_clipboard),
        ):
            try:
                yield pending, snapshot, state, original_formats
            finally:
                snapshot.close()

    def test_restore_retries_empty_and_partial_writes_without_losing_formats(self):
        for failed_write in (1, 2, 3):
            with self.subTest(failed_write=failed_write):
                with self._restore_retry_scenario(fail_writes=(failed_write,)) as scenario:
                    pending, snapshot, state, original_formats = scenario
                    with self.assertRaisesRegex(clipboard.ClipboardError, "write failed"):
                        pending.restore_clipboard()

                    self.assertFalse(snapshot._closed)
                    self.assertFalse(state["locked"])
                    self.assertNotIn(clipboard_paste._MARKER_FORMAT, state["formats"])
                    pending.restore_clipboard()

                    self.assertEqual(state["formats"], original_formats)
                    self.assertEqual(state["empties"], 2)
                    self.assertTrue(snapshot._closed)

    def test_restore_retries_repeated_write_failures(self):
        with self._restore_retry_scenario(fail_writes=(2, 4)) as scenario:
            pending, snapshot, state, original_formats = scenario
            for _attempt in range(2):
                with self.assertRaisesRegex(clipboard.ClipboardError, "write failed"):
                    pending.restore_clipboard()
                self.assertFalse(snapshot._closed)
            pending.restore_clipboard()
            self.assertEqual(state["formats"], original_formats)
            self.assertEqual(state["empties"], 3)
            self.assertTrue(snapshot._closed)

    def test_restore_retry_preserves_external_changes_even_with_same_marker(self):
        for external_formats in (
            {},
            {clipboard.CF_UNICODETEXT: b"new copy"},
            {clipboard_paste._MARKER_FORMAT: b"marker"},
        ):
            with self.subTest(external_formats=external_formats):
                with self._restore_retry_scenario(fail_writes=(2,)) as scenario:
                    pending, snapshot, state, _original_formats = scenario
                    with self.assertRaises(clipboard.ClipboardError):
                        pending.restore_clipboard()
                    state["formats"] = external_formats.copy()
                    state["sequence"] += 1
                    pending.restore_clipboard()
                    self.assertEqual(state["formats"], external_formats)
                    self.assertEqual(state["empties"], 1)
                    self.assertTrue(snapshot._closed)

    def test_restore_retry_keeps_snapshot_when_sequence_is_unavailable(self):
        for available_on_failure in (False, True):
            with self.subTest(available_on_failure=available_on_failure):
                with self._restore_retry_scenario(fail_writes=(1,)) as scenario:
                    pending, snapshot, state, _original_formats = scenario
                    state["sequence_available"] = available_on_failure
                    with self.assertRaisesRegex(clipboard.ClipboardError, "write failed"):
                        pending.restore_clipboard()
                    state["sequence_available"] = False
                    with self.assertRaises(clipboard.ClipboardError):
                        pending.restore_clipboard()
                    self.assertFalse(snapshot._closed)
                    self.assertEqual(state["empties"], 1)
                    self.assertFalse(state["locked"])
                    state["sequence_available"] = True
                    if available_on_failure:
                        pending.restore_clipboard()
                        self.assertTrue(snapshot._closed)
                        self.assertEqual(state["formats"], _original_formats)
                    else:
                        with self.assertRaises(clipboard.ClipboardError):
                            pending.restore_clipboard()
                        self.assertFalse(snapshot._closed)
                        self.assertEqual(state["empties"], 1)

    def test_restore_retries_failure_before_emptying_with_original_marker(self):
        with self._restore_retry_scenario() as scenario:
            pending, snapshot, state, original_formats = scenario
            state["fail_empty"] = True
            with self.assertRaises(clipboard.ClipboardError):
                pending.restore_clipboard()
            self.assertFalse(snapshot._closed)
            state["fail_empty"] = False
            pending.restore_clipboard()
            self.assertEqual(state["formats"], original_formats)
            self.assertEqual(state["empties"], 1)
            self.assertTrue(snapshot._closed)

    def test_restore_cannot_overwrite_a_copy_after_marker_validation(self):
        state = {
            "locked": False,
            "marker": b"marker",
            "text": "snippet",
            "external_copy": False,
        }
        events = []
        original = "original\0".encode("utf-16-le")
        snapshot = ClipboardSnapshot([
            _ClipboardFormatCopy(clipboard.CF_UNICODETEXT, "hglobal", original),
        ])
        pending = PendingPaste(snapshot, b"marker")

        def open_clipboard():
            self.assertFalse(state["locked"])
            state["locked"] = True
            events.append("open")

        def read_marker(format_id):
            self.assertTrue(state["locked"])
            self.assertEqual(format_id, clipboard_paste._MARKER_FORMAT)
            events.append("check")
            return state["marker"]

        def empty_clipboard():
            self.assertTrue(state["locked"])
            state.update(marker=None, text="")
            events.append("empty")
            return True

        def set_data(format_id, data):
            self.assertTrue(state["locked"])
            self.assertEqual(format_id, clipboard.CF_UNICODETEXT)
            self.assertEqual(data, original)
            state["text"] = "original"
            events.append("write")

        def close_clipboard():
            self.assertTrue(state["locked"])
            state["locked"] = False
            events.append("close")
            # A waiting external writer can only publish once the lock is
            # released. The former check/close/restore sequence overwrote it.
            if not state["external_copy"]:
                state.update(marker=None, text="new external copy", external_copy=True)
                events.append("external copy")

        with (
            patch.object(clipboard_paste, "_open_clipboard", side_effect=open_clipboard),
            patch.object(clipboard_snapshot, "_open_clipboard", side_effect=open_clipboard),
            patch.object(clipboard_paste, "_read_clipboard_bytes", side_effect=read_marker),
            patch.object(clipboard_snapshot.user32, "EmptyClipboard", side_effect=empty_clipboard),
            patch.object(clipboard_snapshot, "_set_clipboard_data", side_effect=set_data),
            patch.object(clipboard_snapshot.user32, "CloseClipboard", side_effect=close_clipboard),
        ):
            pending.restore_clipboard()

        self.assertEqual(events, ["open", "check", "empty", "write", "close", "external copy"])
        self.assertEqual(state["text"], "new external copy")
        self.assertFalse(state["locked"])
        self.assertTrue(snapshot._closed)

    def test_restore_preserves_changes_during_native_copy_preparation(self):
        for newer_marker in (None, b"another marker"):
            with self.subTest(marker=newer_marker):
                state = {"marker": b"marker", "text": "snippet"}
                snapshot = ClipboardSnapshot([
                    _ClipboardFormatCopy(clipboard_snapshot.CF_BITMAP, "bitmap", 101),
                ])
                pending = PendingPaste(snapshot, b"marker")

                def copy_image(*_arguments):
                    state.update(marker=newer_marker, text="new external copy")
                    return 201

                with (
                    patch.object(clipboard_snapshot, "_open_clipboard"),
                    patch.object(clipboard_snapshot.user32, "CopyImage", side_effect=copy_image),
                    patch.object(
                        clipboard_paste,
                        "_read_clipboard_bytes",
                        side_effect=lambda _format: state["marker"],
                    ),
                    patch.object(clipboard_snapshot.user32, "EmptyClipboard") as empty,
                    patch.object(clipboard_snapshot.user32, "SetClipboardData") as write,
                    patch.object(clipboard_snapshot.user32, "CloseClipboard") as close,
                    patch.object(clipboard_snapshot.gdi32, "DeleteObject") as delete,
                ):
                    pending.restore_clipboard()

                self.assertEqual(state["text"], "new external copy")
                empty.assert_not_called()
                write.assert_not_called()
                close.assert_called_once_with()
                self.assertEqual([call.args for call in delete.call_args_list], [(201,), (101,)])
                self.assertTrue(snapshot._closed)

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
            patch.object(clipboard_paste, "_set_clipboard_content"),
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

    def test_discard_snapshot_releases_saved_clipboard_data(self):
        snapshot = RecordingClipboardSnapshot()
        pending = PendingPaste(snapshot, b"marker")

        pending.discard_snapshot()

        self.assertEqual(snapshot.close_calls, 1)

    def test_restore_uses_marker_when_it_is_still_available(self):
        snapshot = RecordingClipboardSnapshot()
        pending = PendingPaste(snapshot, b"marker")

        with (
            patch.object(clipboard_paste, "_open_clipboard"),
            patch.object(
                clipboard_paste,
                "_read_clipboard_bytes",
                return_value=b"marker",
            ),
            patch.object(clipboard_paste.user32, "CloseClipboard"),
        ):
            pending.restore_clipboard()

        self.assertEqual(snapshot.restore_calls, 1)
        self.assertEqual(snapshot.close_calls, 0)

    def test_restore_preserves_a_genuine_new_clipboard_value(self):
        snapshot = RecordingClipboardSnapshot()
        pending = PendingPaste(snapshot, b"marker")

        with (
            patch.object(clipboard_paste, "_open_clipboard"),
            patch.object(
                clipboard_paste,
                "_read_clipboard_bytes",
                return_value=b"different marker",
            ),
            patch.object(clipboard_paste.user32, "CloseClipboard"),
        ):
            pending.restore_clipboard()

        self.assertEqual(snapshot.restore_calls, 0)
        self.assertEqual(snapshot.close_calls, 1)

    def test_restore_preserves_identical_text_after_marker_was_removed(self):
        snapshot = RecordingClipboardSnapshot()
        pending = PendingPaste(snapshot, b"marker")

        with (
            patch.object(clipboard_paste, "_open_clipboard"),
            patch.object(
                clipboard_paste,
                "_read_clipboard_bytes",
                return_value=None,
            ),
            patch.object(clipboard_paste.user32, "CloseClipboard"),
        ):
            pending.restore_clipboard()

        self.assertEqual(snapshot.restore_calls, 0)
        self.assertEqual(snapshot.close_calls, 1)


class PasteTextTestCase(unittest.TestCase):
    def test_invalid_target_is_rejected_before_clipboard_replacement(self):
        with (
            patch.object(
                clipboard_paste.windows,
                "matches_window_identity",
                return_value=False,
            ),
            patch.object(
                clipboard_paste,
                "_replace_clipboard",
            ) as replace_clipboard,
        ):
            with self.assertRaises(clipboard_paste.PasteTargetError) as raised:
                clipboard_paste.paste_text(TARGET, "Text")

        self.assertEqual(raised.exception.code, "paste_target_window_missing")
        replace_clipboard.assert_not_called()

    def test_activation_failure_restores_replaced_clipboard(self):
        snapshot = RecordingClipboardSnapshot()
        with (
            patch.object(
                clipboard_paste.windows,
                "matches_window_identity",
                return_value=True,
            ),
            patch.object(
                clipboard_paste,
                "_replace_clipboard",
                return_value=snapshot,
            ),
            patch.object(
                clipboard_paste.windows,
                "activate_window_identity",
                return_value=False,
            ),
            patch.object(
                PendingPaste,
                "restore_clipboard",
            ) as restore_clipboard,
        ):
            with self.assertRaises(clipboard.ClipboardError):
                clipboard_paste.paste_text(TARGET, "Text")

        restore_clipboard.assert_called_once_with()

    def test_activation_and_restore_failures_are_both_preserved(self):
        restore_error = clipboard.ClipboardError("restore failed")
        with (
            patch.object(
                clipboard_paste.windows,
                "matches_window_identity",
                return_value=True,
            ),
            patch.object(
                clipboard_paste,
                "_replace_clipboard",
                return_value=RecordingClipboardSnapshot(),
            ),
            patch.object(
                clipboard_paste.windows,
                "activate_window_identity",
                return_value=False,
            ),
            patch.object(
                PendingPaste,
                "restore_clipboard",
                side_effect=restore_error,
            ),
        ):
            with self.assertRaises(ClipboardRestoreError) as raised:
                clipboard_paste.paste_text(TARGET, "Text")

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
                "_set_clipboard_content",
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
                "_set_clipboard_content",
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
