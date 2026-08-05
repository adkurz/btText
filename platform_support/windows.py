"""Inspect and activate native Windows application windows."""

import ctypes
from ctypes import wintypes
import ntpath
import os

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9


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
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
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


def get_foreground_window() -> int | None:
    """Return the current foreground window handle, if one exists."""
    handle = user32.GetForegroundWindow()
    return int(handle) if handle else None


def is_valid_window(handle: int | None) -> bool:
    """Return whether ``handle`` identifies an existing native window."""
    return bool(handle and user32.IsWindow(handle))


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
    return bool(user32.SetForegroundWindow(handle))
