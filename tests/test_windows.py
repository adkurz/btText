import ctypes
import os
import unittest
from ctypes import wintypes
from unittest.mock import patch

from platform_support import windows


class NativeWindowTestCase(unittest.TestCase):
    def test_update_shutdown_signal_consumes_auto_reset_event(self):
        with (
            patch.object(
                windows.kernel32,
                "CreateEventW",
                return_value=123,
            ) as create_event,
            patch.object(
                windows.kernel32,
                "WaitForSingleObject",
                return_value=windows.WAIT_OBJECT_0,
            ) as wait_for_single_object,
            patch.object(windows.kernel32, "CloseHandle") as close_handle,
        ):
            signal = windows.UpdateShutdownSignal()
            self.assertTrue(signal.consume())
            signal.close()
            signal.close()

        create_event.assert_called_once_with(
            None,
            False,
            False,
            windows.UPDATE_SHUTDOWN_EVENT_NAME,
        )
        wait_for_single_object.assert_called_once_with(123, 0)
        close_handle.assert_called_once_with(123)

    def test_update_shutdown_signal_reports_no_pending_request(self):
        with (
            patch.object(windows.kernel32, "CreateEventW", return_value=123),
            patch.object(
                windows.kernel32,
                "WaitForSingleObject",
                return_value=windows.WAIT_TIMEOUT,
            ),
            patch.object(windows.kernel32, "CloseHandle"),
        ):
            signal = windows.UpdateShutdownSignal()
            self.assertFalse(signal.consume())
            signal.close()

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

    def test_window_identity_captures_handle_thread_and_process(self):
        def set_process_id(_handle, process_id_pointer):
            process_id = ctypes.cast(
                process_id_pointer,
                ctypes.POINTER(wintypes.DWORD),
            )
            process_id.contents.value = 456
            return 789

        with (
            patch.object(windows.user32, "IsWindow", return_value=True),
            patch.object(
                windows.user32,
                "GetWindowThreadProcessId",
                side_effect=set_process_id,
            ),
        ):
            identity = windows.get_window_identity(123)

        self.assertEqual(
            identity,
            windows.WindowIdentity(123, 789, 456),
        )

    def test_reused_window_handle_does_not_match_original_identity(self):
        original = windows.WindowIdentity(123, 789, 456)
        replacement = windows.WindowIdentity(123, 790, 457)

        with patch.object(
            windows,
            "get_window_identity",
            return_value=replacement,
        ):
            self.assertFalse(windows.matches_window_identity(original))

    def test_window_identity_is_rechecked_immediately_before_activation(self):
        identity = windows.WindowIdentity(123, 789, 456)

        with (
            patch.object(
                windows,
                "matches_window_identity",
                return_value=True,
            ) as matches_identity,
            patch.object(windows, "activate_window", return_value=True) as activate,
        ):
            self.assertTrue(windows.activate_window_identity(identity))

        matches_identity.assert_called_once_with(identity)
        activate.assert_called_once_with(identity.handle)

    def test_reused_window_handle_is_not_activated(self):
        identity = windows.WindowIdentity(123, 789, 456)

        with (
            patch.object(
                windows,
                "matches_window_identity",
                return_value=False,
            ),
            patch.object(windows, "activate_window") as activate,
        ):
            self.assertFalse(windows.activate_window_identity(identity))

        activate.assert_not_called()

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
            patch.object(
                windows.user32,
                "GetForegroundWindow",
                return_value=123,
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

    def test_activation_joins_foreground_input_thread_after_direct_failure(self):
        foreground_handles = iter((456, 456, 123))

        with (
            patch.object(windows.user32, "IsWindow", return_value=True),
            patch.object(windows.user32, "ShowWindow"),
            patch.object(windows.user32, "SetForegroundWindow") as set_foreground,
            patch.object(
                windows.user32,
                "GetForegroundWindow",
                side_effect=foreground_handles,
            ),
            patch.object(
                windows.user32,
                "GetWindowThreadProcessId",
                return_value=22,
            ),
            patch.object(
                windows.kernel32,
                "GetCurrentThreadId",
                return_value=11,
            ),
            patch.object(
                windows.user32,
                "AttachThreadInput",
                return_value=True,
            ) as attach_thread_input,
            patch.object(windows.user32, "BringWindowToTop") as bring_to_top,
            patch.object(windows.user32, "SetFocus") as set_focus,
        ):
            self.assertTrue(windows.activate_window(123))

        self.assertEqual(set_foreground.call_count, 2)
        self.assertEqual(
            attach_thread_input.call_args_list,
            [unittest.mock.call(11, 22, True), unittest.mock.call(11, 22, False)],
        )
        bring_to_top.assert_called_once_with(123)
        set_focus.assert_called_once_with(123)

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
