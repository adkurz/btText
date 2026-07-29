"""Paste snippet text into another Windows application via the clipboard."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import uuid

from platform_support import keyboard_input
from platform_support.clipboard import (
    CF_UNICODETEXT,
    ClipboardError,
    _open_clipboard,
    _set_clipboard_data,
    _set_clipboard_text,
    kernel32,
    user32,
)
from platform_support.clipboard_snapshot import ClipboardSnapshot

SW_RESTORE = 9


PasteError = ClipboardError


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


_MARKER_FORMAT = user32.RegisterClipboardFormatW("BTText.PasteMarker")
if not _MARKER_FORMAT:
    raise ctypes.WinError(ctypes.get_last_error())


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


def activate_window(handle: int) -> bool:
    """Restore a valid window and make it the foreground window."""
    if not handle or not user32.IsWindow(handle):
        return False
    user32.ShowWindow(handle, SW_RESTORE)
    return bool(user32.SetForegroundWindow(handle))


def _read_clipboard_bytes(format_id: int) -> bytes | None:
    """Read a global-memory clipboard format while the clipboard is open."""
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


def _read_clipboard_text() -> str | None:
    """Read Unicode text while the clipboard is open, if decodable."""
    data = _read_clipboard_bytes(CF_UNICODETEXT)
    if data is None:
        return None
    try:
        return data.decode("utf-16-le").split("\0", 1)[0]
    except UnicodeDecodeError:
        return None


def _replace_clipboard(text: str, marker: bytes) -> ClipboardSnapshot:
    """Save the clipboard and replace it with marked snippet text."""
    snapshot = ClipboardSnapshot.capture()
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


class PendingPaste:
    """A paste whose complete previous clipboard can be restored later."""

    def __init__(
        self,
        snapshot: ClipboardSnapshot,
        marker: bytes,
        pasted_text: str,
    ):
        """Retain the snapshot and markers for one delayed restoration."""
        self._snapshot = snapshot
        self._marker = marker
        self._pasted_text = pasted_text

    def restore_clipboard(self) -> None:
        """Restore every old format unless another app changed the clipboard."""
        _open_clipboard()
        try:
            marker_matches = _read_clipboard_bytes(_MARKER_FORMAT) == self._marker
            text_matches = _read_clipboard_text() == self._pasted_text
        finally:
            user32.CloseClipboard()
        if marker_matches or text_matches:
            # Some targets preserve the text but strip private formats. The
            # text comparison still identifies our temporary clipboard value.
            self._snapshot.restore()
        else:
            # Respect a newer clipboard change and release the retained object.
            self._snapshot.close()

    def discard_snapshot(self) -> None:
        """Release the saved clipboard data without attempting another restore."""
        self._snapshot.close()


def paste_text(target_window: int, text: str) -> PendingPaste:
    """Activate target_window, put text on the clipboard and send Ctrl+V."""
    if not target_window or not user32.IsWindow(target_window):
        raise PasteError("The previously active window no longer exists.")

    marker = uuid.uuid4().bytes
    pending = PendingPaste(_replace_clipboard(text, marker), marker, text)
    if not activate_window(target_window):
        pending.restore_clipboard()
        raise PasteError("The previously active window could not be activated.")
    try:
        keyboard_input.send_ctrl_v()
    except Exception:
        pending.restore_clipboard()
        raise
    return pending


def expand_hotstring(
    target_window: int,
    text: str,
    hotstring_length: int,
    boundary_key: int | None,
) -> PendingPaste:
    """Replace a typed hotstring and optionally replay its boundary key."""
    if not target_window or not user32.IsWindow(target_window):
        raise PasteError("The active window no longer exists.")
    marker = uuid.uuid4().bytes
    pending = PendingPaste(_replace_clipboard(text, marker), marker, text)
    if not activate_window(target_window):
        pending.restore_clipboard()
        raise PasteError("The active window could not be activated.")
    try:
        keyboard_input.send_virtual_key(0x08, hotstring_length)  # VK_BACK
        keyboard_input.send_ctrl_v()
        if boundary_key is not None:
            keyboard_input.send_virtual_key(boundary_key)
    except Exception:
        pending.restore_clipboard()
        raise
    return pending
