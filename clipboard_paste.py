"""Paste snippet text into another Windows application via the clipboard."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time
import uuid


CF_UNICODETEXT = 13
CF_HDROP = 15
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
ole32 = ctypes.WinDLL("ole32")

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
user32.EnumClipboardFormats.argtypes = (wintypes.UINT,)
user32.EnumClipboardFormats.restype = wintypes.UINT
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

ole32.OleInitialize.argtypes = (wintypes.LPVOID,)
ole32.OleInitialize.restype = ctypes.c_long
ole32.OleUninitialize.restype = None
ole32.OleGetClipboard.argtypes = (ctypes.POINTER(ctypes.c_void_p),)
ole32.OleGetClipboard.restype = ctypes.c_long
ole32.OleSetClipboard.argtypes = (ctypes.c_void_p,)
ole32.OleSetClipboard.restype = ctypes.c_long


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


class _ClipboardSnapshot:
    """A retained OLE IDataObject containing every clipboard format."""

    def __init__(
        self,
        data_object: ctypes.c_void_p,
        copied_formats: list[tuple[int, bytes]],
    ):
        self._data_object = data_object
        self._copied_formats = copied_formats
        self._contains_file_drop = any(
            format_id == CF_HDROP for format_id, _ in copied_formats
        )
        self._closed = False

    @classmethod
    def capture(cls) -> _ClipboardSnapshot:
        # OleInitialize returns S_OK or S_FALSE on success. Both calls must be
        # balanced by OleUninitialize after the retained IDataObject is released.
        result = ole32.OleInitialize(None)
        if result < 0:
            raise PasteError(
                "The clipboard could not be initialized for a complete backup."
            )
        data_object = ctypes.c_void_p()
        result = ole32.OleGetClipboard(ctypes.byref(data_object))
        if result < 0 or not data_object:
            ole32.OleUninitialize()
            raise PasteError("The complete clipboard contents could not be saved.")
        snapshot = cls(data_object, [])
        try:
            snapshot._copied_formats = _copy_hglobal_clipboard_formats()
            snapshot._contains_file_drop = any(
                format_id == CF_HDROP
                for format_id, _ in snapshot._copied_formats
            )
        except Exception:
            snapshot.close()
            raise
        return snapshot

    def restore(self) -> None:
        if self._closed:
            return
        if self._contains_file_drop:
            # Explorer's IDataObject may stop serving CF_HDROP after clipboard
            # ownership changes. Restore the independent HGLOBAL copies instead.
            _restore_copied_formats(self._copied_formats)
        else:
            result = ole32.OleSetClipboard(self._data_object)
            if result < 0:
                raise PasteError(
                    "The complete clipboard contents could not be restored."
                )
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        # IDataObject inherits IUnknown; Release is the third vtable entry.
        vtable = ctypes.cast(
            self._data_object,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
        ).contents
        release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vtable[2])
        release(self._data_object)
        self._closed = True
        ole32.OleUninitialize()

    def __del__(self):
        # Normally restore_clipboard closes the snapshot. This is a safety net
        # for application shutdown while a delayed restore is pending.
        if not self._closed:
            try:
                self.close()
            except Exception:
                pass


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


def _copy_hglobal_clipboard_formats() -> list[tuple[int, bytes]]:
    """Deep-copy all clipboard formats backed by movable global memory."""
    copied_formats: list[tuple[int, bytes]] = []
    _open_clipboard()
    try:
        format_id = 0
        while True:
            format_id = user32.EnumClipboardFormats(format_id)
            if not format_id:
                break
            data = _read_clipboard_bytes(format_id)
            if data is not None:
                copied_formats.append((format_id, data))
    finally:
        user32.CloseClipboard()
    return copied_formats


def _restore_copied_formats(copied_formats: list[tuple[int, bytes]]) -> None:
    """Restore a deep-copied collection of HGLOBAL clipboard formats."""
    _open_clipboard()
    try:
        if not user32.EmptyClipboard():
            raise PasteError("The clipboard could not be restored.")
        for format_id, data in copied_formats:
            _set_clipboard_data(format_id, data)
    finally:
        user32.CloseClipboard()


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
    snapshot = _ClipboardSnapshot.capture()
    try:
        _open_clipboard()
        try:
            if not user32.EmptyClipboard():
                raise PasteError("The clipboard could not be cleared.")
            _set_clipboard_text(text)
            _set_clipboard_data(_MARKER_FORMAT, marker)
        finally:
            user32.CloseClipboard()
        return snapshot
    except Exception:
        # EmptyClipboard may already have discarded the original contents.
        snapshot.restore()
        raise


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
    """A paste whose complete previous clipboard can be restored later."""

    def __init__(self, snapshot: _ClipboardSnapshot, marker: bytes):
        self._snapshot = snapshot
        self._marker = marker

    def restore_clipboard(self) -> None:
        """Restore every old format unless another app changed the clipboard."""
        _open_clipboard()
        try:
            marker_matches = _read_clipboard_bytes(_MARKER_FORMAT) == self._marker
        finally:
            user32.CloseClipboard()
        if marker_matches:
            self._snapshot.restore()
        else:
            # Respect a newer clipboard change and release the retained object.
            self._snapshot.close()


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
