"""Inspect and activate native Windows application windows."""

import ctypes
from ctypes import wintypes
import os


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


def activate_window(handle: int | None) -> bool:
    """Restore a valid window and make it the foreground window."""
    if not is_valid_window(handle):
        return False
    user32.ShowWindow(handle, SW_RESTORE)
    return bool(user32.SetForegroundWindow(handle))
