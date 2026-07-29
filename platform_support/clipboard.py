"""Copy Unicode text to the Windows clipboard with privacy controls."""

import ctypes
import time
from ctypes import wintypes


CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


class ClipboardError(RuntimeError):
    """Raised when Windows cannot complete a clipboard operation."""


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

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


_CLIPBOARD_HISTORY_FORMAT = user32.RegisterClipboardFormatW(
    "CanIncludeInClipboardHistory"
)
if not _CLIPBOARD_HISTORY_FORMAT:
    raise ctypes.WinError(ctypes.get_last_error())
_CLOUD_CLIPBOARD_FORMAT = user32.RegisterClipboardFormatW(
    "CanUploadToCloudClipboard"
)
if not _CLOUD_CLIPBOARD_FORMAT:
    raise ctypes.WinError(ctypes.get_last_error())


def _open_clipboard(attempts: int = 6, delay: float = 0.01) -> None:
    """Open the process-wide clipboard, retrying short-lived contention."""
    for attempt in range(attempts):
        if user32.OpenClipboard(None):
            return
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise ClipboardError("The clipboard is currently in use by another program.")


def _set_clipboard_data(format_id: int, data: bytes) -> None:
    """Copy bytes into movable global memory and transfer it to Windows."""
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise ClipboardError("Not enough memory is available for the clipboard.")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise ClipboardError("The clipboard memory could not be accessed.")
    try:
        ctypes.memmove(pointer, data, len(data))
    finally:
        kernel32.GlobalUnlock(handle)
    if not user32.SetClipboardData(format_id, handle):
        kernel32.GlobalFree(handle)
        raise ClipboardError("The clipboard data could not be set.")


def _set_clipboard_text(text: str) -> None:
    """Write null-terminated UTF-16 text while the clipboard is open."""
    _set_clipboard_data(CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))


def copy_text(
    text: str,
    include_in_history: bool = True,
    allow_cloud_upload: bool = True,
) -> None:
    """Copy text with independent history and cloud-upload controls."""
    _open_clipboard()
    try:
        if not user32.EmptyClipboard():
            raise ClipboardError("The clipboard could not be cleared.")
        _set_clipboard_text(text)
        if not include_in_history:
            # Windows recognizes a serialized DWORD of zero in this registered
            # format as a request to omit the item from clipboard history.
            _set_clipboard_data(_CLIPBOARD_HISTORY_FORMAT, b"\0\0\0\0")
        if not allow_cloud_upload:
            # This registered format controls cross-device synchronization
            # independently from the local clipboard-history setting.
            _set_clipboard_data(_CLOUD_CLIPBOARD_FORMAT, b"\0\0\0\0")
    finally:
        user32.CloseClipboard()
