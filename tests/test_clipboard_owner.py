import unittest
from unittest.mock import Mock, call, patch

from core.rich_text import ClipboardContent
from platform_support import clipboard, clipboard_paste, clipboard_snapshot


class ClipboardOwnerTestCase(unittest.TestCase):
    def test_all_write_paths_keep_an_owner_alive_until_the_clipboard_is_closed(self):
        for operation in ("copy", "paste", "restore"):
            for failure in (None, "create", "open", "empty", "write"):
                with self.subTest(operation=operation, failure=failure):
                    events = []
                    state = {"alive": False, "open": False}
                    owner = 0x123456789

                    def create(*args):
                        events.append("create")
                        self.assertEqual(args[1], "STATIC")
                        self.assertEqual(args[3], 0)
                        self.assertEqual(args[8], clipboard.HWND_MESSAGE)
                        if failure == "create":
                            return None
                        state["alive"] = True
                        return owner

                    def open_clipboard(handle):
                        self.assertTrue(state["alive"])
                        self.assertEqual(handle, owner)
                        events.append("open")
                        if failure == "open":
                            return False
                        state["open"] = True
                        return True

                    def empty():
                        self.assertTrue(state["alive"] and state["open"])
                        events.append("empty")
                        return failure != "empty"

                    def write(*args):
                        self.assertTrue(state["alive"] and state["open"])
                        events.append("write")
                        if failure == "write":
                            raise clipboard.ClipboardError("write failed")

                    def close():
                        self.assertTrue(state["alive"] and state["open"])
                        state["open"] = False
                        events.append("close")
                        return True

                    def destroy(handle):
                        self.assertEqual(handle, owner)
                        self.assertTrue(state["alive"])
                        self.assertFalse(state["open"])
                        state["alive"] = False
                        events.append("destroy")
                        return True

                    snapshot = Mock()
                    with (
                        patch.object(clipboard.user32, "CreateWindowExW", side_effect=create),
                        patch.object(clipboard.user32, "DestroyWindow", side_effect=destroy),
                        patch.object(clipboard.user32, "OpenClipboard", side_effect=open_clipboard),
                        patch.object(clipboard.user32, "EmptyClipboard", side_effect=empty),
                        patch.object(clipboard.user32, "CloseClipboard", side_effect=close),
                        patch.object(clipboard.time, "sleep"),
                        patch.object(clipboard, "_set_clipboard_data", side_effect=write),
                        patch.object(clipboard_paste, "_set_clipboard_data", side_effect=write),
                        patch.object(clipboard_snapshot, "_set_clipboard_data", side_effect=write),
                        patch.object(clipboard_paste.ClipboardSnapshot, "capture", return_value=snapshot) as capture,
                    ):
                        def execute():
                            if operation == "copy":
                                clipboard.copy_content(ClipboardContent("text", "<p>text</p>"))
                            elif operation == "paste":
                                clipboard_paste._replace_clipboard("text", b"marker")
                            else:
                                clipboard_snapshot._restore_copied_formats([
                                    clipboard_snapshot._ClipboardFormatCopy(13, "hglobal", b"text"),
                                ])

                        if failure is None:
                            execute()
                        else:
                            with self.assertRaises(clipboard.ClipboardError):
                                execute()

                    self.assertFalse(state["alive"] or state["open"])
                    if failure == "create":
                        self.assertEqual(events, ["create"])
                        capture.assert_not_called()
                        snapshot.restore.assert_not_called()
                    elif failure == "open":
                        self.assertNotIn("empty", events)
                        self.assertNotIn("close", events)
                        self.assertEqual(events[-1], "destroy")
                    else:
                        self.assertEqual(events[-2:], ["close", "destroy"])

    def test_open_clipboard_retries_with_the_same_owner(self):
        with (
            patch.object(clipboard.user32, "OpenClipboard", side_effect=(False, False, True)) as open_clipboard,
            patch.object(clipboard.time, "sleep") as sleep,
        ):
            clipboard._open_clipboard(owner=123)

        self.assertEqual(open_clipboard.call_args_list, [call(123)] * 3)
        self.assertEqual(sleep.call_count, 2)

    def test_read_only_access_needs_no_owner_window(self):
        with (
            patch.object(clipboard.user32, "CreateWindowExW") as create,
            patch.object(clipboard.user32, "OpenClipboard", return_value=True) as open_clipboard,
            patch.object(clipboard.user32, "CloseClipboard", return_value=True),
            patch.object(clipboard, "_read_open_clipboard_text", return_value="text"),
        ):
            self.assertEqual(clipboard.read_text(), "text")

        open_clipboard.assert_called_once_with(None)
        create.assert_not_called()
