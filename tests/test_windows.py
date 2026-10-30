import ctypes
import os
import subprocess
import sys
import unittest
from ctypes import wintypes
from unittest.mock import Mock, patch

import wx

from platform_support import windows


class ForegroundWindowObserverTestCase(unittest.TestCase):
    def test_native_observer_receives_ordered_events_from_another_process(self):
        app = wx.GetApp() or wx.App(False)
        frame = wx.Frame(None)
        frame.ShowWithoutActivating()
        frame.Hide()
        handles = []
        observed = []

        def on_foreground(handle):
            if handle in handles:
                observed.append(handle)
                if handle == handles[-1]:
                    frame.Destroy()

        observer = windows.ForegroundWindowObserver(on_foreground)
        # Emit actual WinEvents from external, invisible windows. This checks
        # the native callback ABI and wx dispatch without stealing desktop focus
        # or writing to the real clipboard.
        script = """
import ctypes
from ctypes import wintypes
import sys
from platform_support.clipboard import user32
user32.NotifyWinEvent.argtypes = (
    wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG,
)
handles = [
    user32.CreateWindowExW(
        0, 'STATIC', 'btText foreground regression', 0, 0, 0, 10, 10,
        None, None, None, None,
    ) for _ in range(2)
]
print(*handles, flush=True)
sys.stdin.readline()
for handle in handles:
    user32.NotifyWinEvent(3, handle, 0, 0)
sys.stdin.readline()
for handle in handles:
    user32.DestroyWindow(handle)
"""
        child = None
        timeout = None
        try:
            child = subprocess.Popen(
                [sys.executable, "-c", script], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            handles.extend(int(value) for value in child.stdout.readline().split())
            self.assertEqual(len(handles), 2)
            self.assertTrue(all(handles))

            def emit_events():
                child.stdin.write("\n")
                child.stdin.flush()

            wx.CallAfter(emit_events)
            timeout = wx.CallLater(3000, frame.Destroy)
            app.MainLoop()
            self.assertEqual(observed, handles)
        finally:
            if timeout is not None:
                timeout.Stop()
            observer.close()
            if frame:
                frame.Destroy()
            if child is not None:
                try:
                    child.communicate("\n", timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate()

    def test_observer_delivers_the_event_window_and_releases_the_hook(self):
        listener = Mock()
        with (
            patch.object(windows.user32, "SetWinEventHook", return_value=123) as register,
            patch.object(windows.user32, "UnhookWinEvent", return_value=True) as unregister,
        ):
            observer = windows.ForegroundWindowObserver(listener)
            callback = register.call_args.args[3]
            # The event can be delivered after the shell has become foreground.
            with patch.object(windows, "get_foreground_window", return_value=999):
                callback(123, windows.EVENT_SYSTEM_FOREGROUND, 42, 0, 0, 7, 100)
            listener.assert_called_once_with(42)
            observer.close()
            observer.close()
            callback(123, windows.EVENT_SYSTEM_FOREGROUND, 84, 0, 0, 8, 101)

        register.assert_called_once_with(
            windows.EVENT_SYSTEM_FOREGROUND, windows.EVENT_SYSTEM_FOREGROUND,
            None, callback, 0, 0, windows.WINEVENT_SKIPOWNPROCESS,
        )
        unregister.assert_called_once_with(123)
        listener.assert_called_once_with(42)

    def test_observer_rejects_failed_registration(self):
        with patch.object(windows.user32, "SetWinEventHook", return_value=None):
            with self.assertRaises(OSError):
                windows.ForegroundWindowObserver(Mock())

    def test_callback_failure_does_not_escape_into_windows(self):
        with (
            patch.object(windows.user32, "SetWinEventHook", return_value=123),
            patch.object(windows.user32, "UnhookWinEvent", return_value=True),
            self.assertLogs("bttext.windows", level="ERROR"),
        ):
            observer = windows.ForegroundWindowObserver(Mock(side_effect=RuntimeError("failed")))
            try:
                observer._callback(123, windows.EVENT_SYSTEM_FOREGROUND, 42, 0, 0, 7, 100)
            finally:
                observer.close()

    def test_shell_surfaces_are_excluded_but_explorer_folders_are_allowed(self):
        for class_name in (*windows._SHELL_WINDOW_CLASSES, "CabinetWClass", "Notepad"):
            with self.subTest(class_name=class_name):
                def get_class_name(handle, buffer, size):
                    buffer.value = class_name
                    return len(class_name)

                with (
                    patch.object(windows.user32, "GetClassNameW", side_effect=get_class_name),
                    patch.object(windows.user32, "GetAncestor", return_value=42),
                ):
                    self.assertEqual(
                        windows.is_shell_window(42),
                        class_name in windows._SHELL_WINDOW_CLASSES,
                    )

    def test_tray_overflow_popup_and_owned_context_menu_are_not_paste_targets(self):
        classes = {
            42: "Notepad",
            100: "Shell_TrayWnd",
            101: "TopLevelWindowForOverflowXamlIsland",
            102: "Xaml_WindowedPopupClass",
            103: "#32768",
            104: "ThumbnailDeviceHelperWnd",
            105: "UnrecognizedPopupClass",
            200: "#32770",  # A normal application dialog remains usable.
        }
        owners = {102: 101, 103: 101, 105: 100, 200: 42}

        def get_class_name(handle, buffer, size):
            buffer.value = classes[handle]
            return len(buffer.value)

        with (
            patch.object(windows.user32, "GetClassNameW", side_effect=get_class_name),
            patch.object(windows.user32, "GetAncestor", side_effect=lambda h, flag: owners.get(h, h)),
        ):
            for handle in (100, 101, 102, 103, 104, 105):
                with self.subTest(handle=handle):
                    self.assertTrue(windows.is_shell_window(handle))
            self.assertFalse(windows.is_shell_window(42))
            self.assertFalse(windows.is_shell_window(200))

    def test_unknown_window_is_not_accepted_as_an_application(self):
        with patch.object(windows.user32, "GetClassNameW", return_value=0):
            self.assertTrue(windows.is_shell_window(42))


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

    def test_activation_restores_original_child_focus_across_threads(self):
        identity = windows.WindowIdentity(123, 789, 456)
        with (
            patch.object(windows, "matches_window_identity", return_value=True),
            patch.object(windows, "activate_window", return_value=True),
            patch.object(windows, "get_foreground_window", return_value=123),
            patch.object(windows.user32, "IsChild", return_value=True),
            patch.object(windows.user32, "GetWindowThreadProcessId", return_value=789),
            patch.object(windows.kernel32, "GetCurrentThreadId", return_value=999),
            patch.object(windows.user32, "AttachThreadInput", return_value=True) as attach,
            patch.object(windows.user32, "SetFocus") as focus,
            patch.object(windows.user32, "GetFocus", return_value=124),
        ):
            self.assertTrue(windows.activate_window_identity(identity, focus_window=124))
        focus.assert_called_once_with(124)
        self.assertEqual([call.args for call in attach.call_args_list], [(999, 789, True), (999, 789, False)])

    def test_activation_rejects_a_missing_or_reparented_original_child(self):
        identity = windows.WindowIdentity(123, 789, 456)
        with (
            patch.object(windows, "matches_window_identity", return_value=True),
            patch.object(windows, "activate_window", return_value=True),
            patch.object(windows.user32, "IsChild", return_value=False),
            patch.object(windows.user32, "AttachThreadInput") as attach,
            patch.object(windows.user32, "SetFocus") as focus,
        ):
            self.assertFalse(windows.activate_window_identity(identity, focus_window=124))
        attach.assert_not_called()
        focus.assert_not_called()

    def test_activation_without_a_captured_focus_handle_requires_no_child_focus(self):
        identity = windows.WindowIdentity(123, 789, 456)
        for focus_window in (None, 0):
            with (
                self.subTest(focus_window=focus_window),
                patch.object(windows, "matches_window_identity", return_value=True),
                patch.object(windows, "activate_window", return_value=True),
                patch.object(windows.user32, "IsChild") as is_child,
                patch.object(windows.user32, "GetFocus") as get_focus,
                patch.object(windows.user32, "SetFocus") as set_focus,
            ):
                self.assertTrue(windows.activate_window_identity(
                    identity, focus_window=focus_window,
                ))
            is_child.assert_not_called()
            get_focus.assert_not_called()
            set_focus.assert_not_called()

    def test_original_focus_can_be_the_top_level_window_itself(self):
        identity = windows.WindowIdentity(123, 789, 456)
        with (
            patch.object(windows, "matches_window_identity", return_value=True),
            patch.object(windows, "activate_window", return_value=True),
            patch.object(windows, "get_foreground_window", return_value=123),
            patch.object(windows.user32, "IsChild", return_value=False) as is_child,
            patch.object(windows.user32, "GetWindowThreadProcessId", return_value=789),
            patch.object(windows.kernel32, "GetCurrentThreadId", return_value=999),
            patch.object(windows.user32, "AttachThreadInput", return_value=True),
            patch.object(windows.user32, "SetFocus") as focus,
            patch.object(windows.user32, "GetFocus", return_value=123),
        ):
            self.assertTrue(windows.activate_window_identity(identity, focus_window=123))
        is_child.assert_not_called()
        focus.assert_called_once_with(123)

    def test_child_disappearing_during_thread_attachment_is_rejected(self):
        identity = windows.WindowIdentity(123, 789, 456)
        with (
            patch.object(windows, "matches_window_identity", return_value=True),
            patch.object(windows, "activate_window", return_value=True),
            patch.object(windows.user32, "IsChild", side_effect=[True, False]),
            patch.object(windows.user32, "GetWindowThreadProcessId", return_value=789),
            patch.object(windows.kernel32, "GetCurrentThreadId", return_value=999),
            patch.object(windows.user32, "AttachThreadInput", return_value=True) as attach,
            patch.object(windows.user32, "SetFocus") as focus,
        ):
            self.assertFalse(windows.activate_window_identity(identity, focus_window=124))
        focus.assert_not_called()
        attach.assert_called_with(999, 789, False)

    def test_child_focus_restoration_fails_without_thread_access(self):
        identity = windows.WindowIdentity(123, 789, 456)
        with (
            patch.object(windows, "matches_window_identity", return_value=True),
            patch.object(windows, "activate_window", return_value=True),
            patch.object(windows.user32, "IsChild", return_value=True),
            patch.object(windows.user32, "GetWindowThreadProcessId", return_value=789),
            patch.object(windows.kernel32, "GetCurrentThreadId", return_value=999),
            patch.object(windows.user32, "AttachThreadInput", return_value=False),
            patch.object(windows.user32, "SetFocus") as focus,
        ):
            self.assertFalse(windows.activate_window_identity(identity, focus_window=124))
        focus.assert_not_called()

    def test_child_focus_is_not_restored_to_reused_target_after_activation(self):
        identity = windows.WindowIdentity(123, 789, 456)
        with (
            patch.object(windows, "matches_window_identity", side_effect=[True, False]),
            patch.object(windows, "activate_window", return_value=True),
            patch.object(windows.user32, "IsChild", return_value=True),
            patch.object(windows.user32, "GetWindowThreadProcessId", return_value=789),
            patch.object(windows.kernel32, "GetCurrentThreadId", return_value=999),
            patch.object(windows.user32, "AttachThreadInput", return_value=True) as attach,
            patch.object(windows.user32, "SetFocus") as focus,
        ):
            self.assertFalse(windows.activate_window_identity(identity, focus_window=124))
        focus.assert_not_called()
        attach.assert_called_with(999, 789, False)

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

    def test_activation_restores_minimized_window_before_foreground_request(self):
        calls = []

        with (
            patch.object(windows.user32, "IsWindow", return_value=True),
            patch.object(windows.user32, "IsIconic", return_value=True),
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

    def test_activation_preserves_non_minimized_window_placement(self):
        with (
            patch.object(windows.user32, "IsWindow", return_value=True),
            patch.object(windows.user32, "IsIconic", return_value=False) as is_iconic,
            patch.object(windows.user32, "ShowWindow") as show_window,
            patch.object(windows.user32, "SetForegroundWindow") as set_foreground,
            patch.object(windows.user32, "GetForegroundWindow", return_value=123),
        ):
            self.assertTrue(windows.activate_window(123))

        is_iconic.assert_called_once_with(123)
        show_window.assert_not_called()
        set_foreground.assert_called_once_with(123)

    def test_activation_joins_foreground_input_thread_after_direct_failure(self):
        foreground_handles = iter((456, 456, 123))

        with (
            patch.object(windows.user32, "IsWindow", return_value=True),
            patch.object(windows.user32, "IsIconic", return_value=False),
            patch.object(windows.user32, "ShowWindow") as show_window,
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
        show_window.assert_not_called()
        self.assertEqual(
            attach_thread_input.call_args_list,
            [unittest.mock.call(11, 22, True), unittest.mock.call(11, 22, False)],
        )
        bring_to_top.assert_called_once_with(123)
        set_focus.assert_called_once_with(123)

    def test_invalid_window_is_not_activated(self):
        with (
            patch.object(windows.user32, "IsWindow", return_value=False),
            patch.object(windows.user32, "IsIconic") as is_iconic,
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
        is_iconic.assert_not_called()
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
