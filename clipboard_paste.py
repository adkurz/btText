"""Paste snippet text into another Windows application via the clipboard."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import time
import uuid


CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
SW_RESTORE = 9
VK_CONTROL = 0x11
VK_V = 0x56


class PasteError(RuntimeError):
    """Raised when Windows cannot complete a paste operation."""


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
)
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.RegisterClipboardFormatW.argtypes = (wintypes.LPCWSTR,)
user32.RegisterClipboardFormatW.restype = wintypes.UINT
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.IsClipboardFormatAvailable.argtypes = (wintypes.UINT,)
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE

kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalSize.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalSize.restype = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = (("type", wintypes.DWORD), ("data", _INPUTUNION))


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


_MARKER_FORMAT = user32.RegisterClipboardFormatW("BTText.PasteMarker")
if not _MARKER_FORMAT:
    raise ctypes.WinError(ctypes.get_last_error())


@dataclass(frozen=True)
class _ClipboardSnapshot:
    had_text: bool
    text: str


def get_foreground_window() -> int | None:
    """Return the current foreground window handle, if one exists."""
    handle = user32.GetForegroundWindow()
    return int(handle) if handle else None


def is_external_window(handle: int | None) -> bool:
    """Return whether handle belongs to another process and is still valid."""
    if not handle or not user32.IsWindow(handle):
        return False
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    return process_id.value != os.getpid()


def _open_clipboard(attempts: int = 6, delay: float = 0.01) -> None:
    for attempt in range(attempts):
        if user32.OpenClipboard(None):
            return
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise PasteError("The clipboard is currently in use by another program.")


def _read_clipboard_bytes(format_id: int) -> bytes | None:
    if not user32.IsClipboardFormatAvailable(format_id):
        return None
    handle = user32.GetClipboardData(format_id)
    if not handle:
        return None
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return None
    try:
        return ctypes.string_at(pointer, kernel32.GlobalSize(handle))
    finally:
        kernel32.GlobalUnlock(handle)


def _read_clipboard_text() -> _ClipboardSnapshot:
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return _ClipboardSnapshot(False, "")
    handle = user32.GetClipboardData(CF_UNICODETEXT)
    if not handle:
        return _ClipboardSnapshot(False, "")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        raise PasteError("The text in the clipboard could not be read.")
    try:
        return _ClipboardSnapshot(True, ctypes.wstring_at(pointer))
    finally:
        kernel32.GlobalUnlock(handle)


def _set_clipboard_data(format_id: int, data: bytes) -> None:
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise PasteError("Not enough memory is available for the clipboard.")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise PasteError("The clipboard memory could not be accessed.")
    try:
        ctypes.memmove(pointer, data, len(data))
    finally:
        kernel32.GlobalUnlock(handle)
    if not user32.SetClipboardData(format_id, handle):
        kernel32.GlobalFree(handle)
        raise PasteError("The clipboard data could not be set.")


def _set_clipboard_text(text: str) -> None:
    _set_clipboard_data(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))


def _replace_clipboard(text: str, marker: bytes) -> _ClipboardSnapshot:
    _open_clipboard()
    try:
        snapshot = _read_clipboard_text()
        if not user32.EmptyClipboard():
            raise PasteError("The clipboard could not be cleared.")
        _set_clipboard_text(text)
        _set_clipboard_data(_MARKER_FORMAT, marker)
        return snapshot
    finally:
        user32.CloseClipboard()


def _send_ctrl_v() -> None:
    def keyboard_input(key: int, flags: int = 0) -> INPUT:
        value = INPUT()
        value.type = INPUT_KEYBOARD
        value.ki = KEYBDINPUT(key, 0, flags, 0, 0)
        return value

    keys = (INPUT * 4)(
        keyboard_input(VK_CONTROL),
        keyboard_input(VK_V),
        keyboard_input(VK_V, KEYEVENTF_KEYUP),
        keyboard_input(VK_CONTROL, KEYEVENTF_KEYUP),
    )
    if user32.SendInput(len(keys), keys, ctypes.sizeof(INPUT)) != len(keys):
        raise PasteError("The Ctrl+V keystroke could not be sent.")


class PendingPaste:
    """A paste whose previous clipboard text can be restored later."""

    def __init__(self, snapshot: _ClipboardSnapshot, marker: bytes):
        self._snapshot = snapshot
        self._marker = marker

    def restore_clipboard(self) -> None:
        """Restore old text unless another application changed the clipboard."""
        _open_clipboard()
        try:
            if _read_clipboard_bytes(_MARKER_FORMAT) != self._marker:
                return
            if not user32.EmptyClipboard():
                raise PasteError("The clipboard could not be restored.")
            if self._snapshot.had_text:
                _set_clipboard_text(self._snapshot.text)
        finally:
            user32.CloseClipboard()


def paste_text(target_window: int, text: str) -> PendingPaste:
    """Activate target_window, put text on the clipboard and send Ctrl+V."""
    if not target_window or not user32.IsWindow(target_window):
        raise PasteError("The previously active window no longer exists.")

    marker = uuid.uuid4().bytes
    pending = PendingPaste(_replace_clipboard(text, marker), marker)
    user32.ShowWindow(target_window, SW_RESTORE)
    if not user32.SetForegroundWindow(target_window):
        pending.restore_clipboard()
        raise PasteError("The previously active window could not be activated.")
    try:
        _send_ctrl_v()
    except Exception:
        pending.restore_clipboard()
        raise
    return pending
