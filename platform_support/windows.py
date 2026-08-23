"""Inspect and activate native Windows application windows."""

import ctypes
import ntpath
import os
from ctypes import wintypes
from dataclasses import dataclass

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
UPDATE_SHUTDOWN_EVENT_NAME = r"Local\btText.UpdateShutdown"


@dataclass(frozen=True)
class WindowIdentity:
    """Stable ownership information captured for a native window handle."""

    handle: int
    thread_id: int
    process_id: int


user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
)
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.AttachThreadInput.argtypes = (
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.BOOL,
)
user32.AttachThreadInput.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
user32.SetFocus.argtypes = (wintypes.HWND,)
user32.SetFocus.restype = wintypes.HWND
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = (
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CreateEventW.argtypes = (
    wintypes.LPVOID,
    wintypes.BOOL,
    wintypes.BOOL,
    wintypes.LPCWSTR,
)
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
kernel32.WaitForSingleObject.restype = wintypes.DWORD


class UpdateShutdownSignal:
    """Expose an auto-reset event through which the installer requests exit."""

    def __init__(self) -> None:
        """Create the process-owned side of the per-session update signal."""
        self._handle = kernel32.CreateEventW(
            None,
            False,
            False,
            UPDATE_SHUTDOWN_EVENT_NAME,
        )
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def consume(self) -> bool:
        """Return and reset a pending installer shutdown request."""
        if not self._handle:
            return False
        result = kernel32.WaitForSingleObject(self._handle, 0)
        if result == WAIT_OBJECT_0:
            return True
        if result == WAIT_TIMEOUT:
            return False
        raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        """Release the process-owned event handle; repeated calls are safe."""
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None


def get_foreground_window() -> int | None:
    """Return the current foreground window handle, if one exists."""
    handle = user32.GetForegroundWindow()
    return int(handle) if handle else None


def is_valid_window(handle: int | None) -> bool:
    """Return whether ``handle`` identifies an existing native window."""
    return bool(handle and user32.IsWindow(handle))


def get_window_identity(handle: int | None) -> WindowIdentity | None:
    """Capture ownership so a subsequently reused HWND can be rejected."""
    if not is_valid_window(handle):
        return None
    process_id = wintypes.DWORD()
    thread_id = user32.GetWindowThreadProcessId(
        handle,
        ctypes.byref(process_id),
    )
    if not thread_id or not process_id.value:
        return None
    return WindowIdentity(int(handle), int(thread_id), int(process_id.value))


def matches_window_identity(identity: WindowIdentity) -> bool:
    """Return whether an HWND still belongs to its captured owner."""
    return get_window_identity(identity.handle) == identity


def is_external_window(handle: int | None) -> bool:
    """Return whether handle belongs to another process and is still valid."""
    if not is_valid_window(handle):
        return False
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    return process_id.value != os.getpid()


def get_window_application_name(handle: int | None) -> str | None:
    """Return a window's executable filename without exposing its full path."""
    if not is_valid_window(handle):
        return None
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    if not process_id.value:
        return None
    process = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        process_id.value,
    )
    if not process:
        return None
    try:
        capacity = wintypes.DWORD(32768)
        path_buffer = ctypes.create_unicode_buffer(capacity.value)
        if not kernel32.QueryFullProcessImageNameW(
            process,
            0,
            path_buffer,
            ctypes.byref(capacity),
        ):
            return None
        return ntpath.basename(path_buffer.value) or None
    finally:
        kernel32.CloseHandle(process)


def activate_window(handle: int | None) -> bool:
    """Restore a valid window and make it the foreground window."""
    if not is_valid_window(handle):
        return False
    user32.ShowWindow(handle, SW_RESTORE)
    user32.SetForegroundWindow(handle)
    if get_foreground_window() == handle:
        return True

    foreground_window = get_foreground_window()
    if not foreground_window:
        return False
    foreground_thread = user32.GetWindowThreadProcessId(
        foreground_window,
        None,
    )
    current_thread = kernel32.GetCurrentThreadId()
    if not foreground_thread or foreground_thread == current_thread:
        return False
    if not user32.AttachThreadInput(current_thread, foreground_thread, True):
        return False
    try:
        user32.BringWindowToTop(handle)
        user32.SetForegroundWindow(handle)
        user32.SetFocus(handle)
    finally:
        user32.AttachThreadInput(current_thread, foreground_thread, False)
    return get_foreground_window() == handle
