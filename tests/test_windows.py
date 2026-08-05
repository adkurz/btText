import ctypes
import os
import unittest
from ctypes import wintypes
from unittest.mock import patch

from platform_support import windows


class NativeWindowTestCase(unittest.TestCase):
    def test_missing_foreground_window_returns_none(self):
        with patch.object(
            windows.user32,
            "GetForegroundWindow",
            return_value=None,
        ):
            self.assertIsNone(windows.get_foreground_window())

    def test_invalid_handle_is_not_a_valid_window(self):
        with patch.object(
            windows.user32,
            "IsWindow",
            return_value=False,
        ):
            self.assertFalse(windows.is_valid_window(123))

    def test_own_process_window_is_not_external(self):
        def set_process_id(_handle, process_id_pointer):
            process_id = ctypes.cast(
                process_id_pointer,
                ctypes.POINTER(wintypes.DWORD),
            )
            process_id.contents.value = os.getpid()
            return 1

        with (
            patch.object(windows.user32, "IsWindow", return_value=True),
            patch.object(
                windows.user32,
                "GetWindowThreadProcessId",
                side_effect=set_process_id,
            ),
        ):
            self.assertFalse(windows.is_external_window(123))

    def test_other_process_window_is_external(self):
        def set_process_id(_handle, process_id_pointer):
            process_id = ctypes.cast(
                process_id_pointer,
                ctypes.POINTER(wintypes.DWORD),
            )
            process_id.contents.value = os.getpid() + 1
            return 1

        with (
            patch.object(windows.user32, "IsWindow", return_value=True),
            patch.object(
                windows.user32,
                "GetWindowThreadProcessId",
                side_effect=set_process_id,
            ),
        ):
            self.assertTrue(windows.is_external_window(123))

    def test_activation_restores_window_before_foreground_request(self):
        calls = []

        with (
            patch.object(windows.user32, "IsWindow", return_value=True),
            patch.object(
                windows.user32,
                "ShowWindow",
                side_effect=lambda handle, command: calls.append(
                    ("show", handle, command)
                ),
            ),
            patch.object(
                windows.user32,
                "SetForegroundWindow",
                side_effect=lambda handle: calls.append(
                    ("foreground", handle)
                )
                or True,
            ),
        ):
            self.assertTrue(windows.activate_window(123))

        self.assertEqual(
            calls,
            [
                ("show", 123, windows.SW_RESTORE),
                ("foreground", 123),
            ],
        )

    def test_invalid_window_is_not_activated(self):
        with (
            patch.object(windows.user32, "IsWindow", return_value=False),
            patch.object(
                windows.user32,
                "ShowWindow",
            ) as show_window,
            patch.object(
                windows.user32,
                "SetForegroundWindow",
            ) as set_foreground_window,
        ):
            self.assertFalse(windows.activate_window(123))

        show_window.assert_not_called()
        set_foreground_window.assert_not_called()

    def test_window_application_name_returns_executable_basename(self):
        def set_process_id(_handle, process_id_pointer):
            process_id = ctypes.cast(
                process_id_pointer,
                ctypes.POINTER(wintypes.DWORD),
            )
            process_id.contents.value = 456
            return 1

        def set_image_name(_process, _flags, path_buffer, size_pointer):
            path_buffer.value = r"C:\Windows\System32\notepad.exe"
            size = ctypes.cast(size_pointer, ctypes.POINTER(wintypes.DWORD))
            size.contents.value = len(path_buffer.value)
            return True

        with (
            patch.object(windows.user32, "IsWindow", return_value=True),
            patch.object(
                windows.user32,
                "GetWindowThreadProcessId",
                side_effect=set_process_id,
            ),
            patch.object(
                windows.kernel32,
                "OpenProcess",
                return_value=789,
            ),
            patch.object(
                windows.kernel32,
                "QueryFullProcessImageNameW",
                side_effect=set_image_name,
            ),
            patch.object(windows.kernel32, "CloseHandle") as close_handle,
        ):
            result = windows.get_window_application_name(123)

        self.assertEqual(result, "notepad.exe")
        close_handle.assert_called_once_with(789)

    def test_window_application_name_closes_process_after_query_failure(self):
        def set_process_id(_handle, process_id_pointer):
            process_id = ctypes.cast(
                process_id_pointer,
                ctypes.POINTER(wintypes.DWORD),
            )
            process_id.contents.value = 456
            return 1

        with (
            patch.object(windows.user32, "IsWindow", return_value=True),
            patch.object(
                windows.user32,
                "GetWindowThreadProcessId",
                side_effect=set_process_id,
            ),
            patch.object(windows.kernel32, "OpenProcess", return_value=789),
            patch.object(
                windows.kernel32,
                "QueryFullProcessImageNameW",
                return_value=False,
            ),
            patch.object(windows.kernel32, "CloseHandle") as close_handle,
        ):
            result = windows.get_window_application_name(123)

        self.assertIsNone(result)
        close_handle.assert_called_once_with(789)

    def test_invalid_window_has_no_application_name(self):
        with (
            patch.object(windows.user32, "IsWindow", return_value=False),
            patch.object(windows.kernel32, "OpenProcess") as open_process,
        ):
            result = windows.get_window_application_name(123)

        self.assertIsNone(result)
        open_process.assert_not_called()
