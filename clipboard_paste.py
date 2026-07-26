"""Paste snippet text into another Windows application via the clipboard."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import time
import uuid


CF_UNICODETEXT = 13
CF_BITMAP = 2
CF_METAFILEPICT = 3
CF_PALETTE = 9
CF_ENHMETAFILE = 14
CF_OWNERDISPLAY = 0x0080
CF_DSPBITMAP = 0x0082
CF_DSPMETAFILEPICT = 0x0083
CF_DSPENHMETAFILE = 0x008E
GMEM_MOVEABLE = 0x0002
IMAGE_BITMAP = 0
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

gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.CopyImage.argtypes = (
    wintypes.HANDLE,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
)
user32.CopyImage.restype = wintypes.HANDLE
gdi32.GetPaletteEntries.argtypes = (
    wintypes.HANDLE,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.LPVOID,
)
gdi32.GetPaletteEntries.restype = wintypes.UINT
gdi32.CreatePalette.argtypes = (wintypes.LPVOID,)
gdi32.CreatePalette.restype = wintypes.HANDLE
gdi32.CopyMetaFileW.argtypes = (wintypes.HANDLE, wintypes.LPCWSTR)
gdi32.CopyMetaFileW.restype = wintypes.HANDLE
gdi32.CopyEnhMetaFileW.argtypes = (wintypes.HANDLE, wintypes.LPCWSTR)
gdi32.CopyEnhMetaFileW.restype = wintypes.HANDLE
gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
gdi32.DeleteMetaFile.argtypes = (wintypes.HANDLE,)
gdi32.DeleteEnhMetaFile.argtypes = (wintypes.HANDLE,)


class KEYBDINPUT(ctypes.Structure):
    """Windows keyboard-input payload used by ``SendInput``."""
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class MOUSEINPUT(ctypes.Structure):
    """Windows mouse-input payload required by the ``INPUT`` union."""
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class HARDWAREINPUT(ctypes.Structure):
    """Windows hardware-input payload required by the ``INPUT`` union."""
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    """Union of the native input payload variants."""
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    """Native input event passed to the Windows ``SendInput`` API."""
    _anonymous_ = ("data",)
    _fields_ = (("type", wintypes.DWORD), ("data", _INPUTUNION))


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


_MARKER_FORMAT = user32.RegisterClipboardFormatW("BTText.PasteMarker")
if not _MARKER_FORMAT:
    raise ctypes.WinError(ctypes.get_last_error())
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


class METAFILEPICT(ctypes.Structure):
    """Native clipboard wrapper for a classic Windows metafile."""
    _fields_ = (
        ("mm", wintypes.LONG),
        ("xExt", wintypes.LONG),
        ("yExt", wintypes.LONG),
        ("hMF", wintypes.HANDLE),
    )


def _copy_palette(handle: int) -> int:
    """Duplicate a GDI palette and return the independently owned handle."""
    entry_count = gdi32.GetPaletteEntries(handle, 0, 0, None)
    if not entry_count:
        raise PasteError("A palette on the clipboard could not be read.")
    # LOGPALETTE is two WORDs followed by PALETTEENTRY[palNumEntries].
    buffer = ctypes.create_string_buffer(4 + entry_count * 4)
    header = ctypes.cast(buffer, ctypes.POINTER(wintypes.WORD))
    header[0] = 0x0300
    header[1] = entry_count
    entries = ctypes.byref(buffer, 4)
    if gdi32.GetPaletteEntries(handle, 0, entry_count, entries) != entry_count:
        raise PasteError("A palette on the clipboard could not be copied.")
    copy = gdi32.CreatePalette(buffer)
    if not copy:
        raise PasteError("A palette on the clipboard could not be copied.")
    return int(copy)


@dataclass
class _ClipboardFormatCopy:
    """One independently owned clipboard-format value and its storage kind."""
    format_id: int
    kind: str
    value: bytes | int | tuple[int, int, int, int]

    def release(self) -> None:
        """Release the retained native object unless ownership was transferred."""
        if not isinstance(self.value, int):
            if self.kind == "metafile" and isinstance(self.value, tuple):
                gdi32.DeleteMetaFile(self.value[3])
            return
        if self.kind in ("bitmap", "palette"):
            gdi32.DeleteObject(self.value)
        elif self.kind == "enhmetafile":
            gdi32.DeleteEnhMetaFile(self.value)


class _ClipboardSnapshot:
    """Independent copies of all materialized Windows clipboard formats."""

    def __init__(
        self,
        copied_formats: list[_ClipboardFormatCopy],
    ):
        """Own copied formats until they are restored or explicitly discarded."""
        self._copied_formats = copied_formats
        self._closed = False

    @classmethod
    def capture(cls) -> _ClipboardSnapshot:
        """Capture all transferable formats from the current clipboard."""
        return cls(_copy_clipboard_formats())

    def restore(self) -> None:
        """Replace the clipboard with this snapshot and close it."""
        if self._closed:
            return
        _restore_copied_formats(self._copied_formats)
        self.close()

    def close(self) -> None:
        """Release all retained native resources without restoring them."""
        if self._closed:
            return
        for copied_format in self._copied_formats:
            copied_format.release()
        self._copied_formats.clear()
        self._closed = True

    def __del__(self):
        """Best-effort fallback for snapshots abandoned during shutdown."""
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


def activate_window(handle: int) -> bool:
    """Restore a valid window and make it the foreground window."""
    if not handle or not user32.IsWindow(handle):
        return False
    user32.ShowWindow(handle, SW_RESTORE)
    return bool(user32.SetForegroundWindow(handle))


def _open_clipboard(attempts: int = 6, delay: float = 0.01) -> None:
    """Open the process-wide clipboard, retrying short-lived contention."""
    for attempt in range(attempts):
        if user32.OpenClipboard(None):
            return
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise PasteError("The clipboard is currently in use by another program.")


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


def _copy_clipboard_format(format_id: int) -> _ClipboardFormatCopy | None:
    """Copy one format according to the ownership rules of its storage type."""
    handle = user32.GetClipboardData(format_id)
    if not handle:
        # CF_OWNERDISPLAY deliberately has no transferable data handle.
        if format_id == CF_OWNERDISPLAY:
            return None
        raise PasteError("A clipboard format could not be read.")

    if format_id in (CF_BITMAP, CF_DSPBITMAP):
        copy = user32.CopyImage(handle, IMAGE_BITMAP, 0, 0, 0)
        kind = "bitmap"
    elif format_id == CF_PALETTE:
        copy = _copy_palette(handle)
        kind = "palette"
    elif format_id in (CF_ENHMETAFILE, CF_DSPENHMETAFILE):
        copy = gdi32.CopyEnhMetaFileW(handle, None)
        kind = "enhmetafile"
    elif format_id in (CF_METAFILEPICT, CF_DSPMETAFILEPICT):
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise PasteError("A metafile on the clipboard could not be accessed.")
        try:
            source = ctypes.cast(pointer, ctypes.POINTER(METAFILEPICT)).contents
            metafile = gdi32.CopyMetaFileW(source.hMF, None)
            if not metafile:
                raise PasteError("A metafile on the clipboard could not be copied.")
            return _ClipboardFormatCopy(
                format_id,
                "metafile",
                (source.mm, source.xExt, source.yExt, int(metafile)),
            )
        finally:
            kernel32.GlobalUnlock(handle)
    else:
        size = kernel32.GlobalSize(handle)
        if not size:
            raise PasteError("A clipboard memory block could not be measured.")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise PasteError("A clipboard memory block could not be accessed.")
        try:
            return _ClipboardFormatCopy(
                format_id, "hglobal", ctypes.string_at(pointer, size)
            )
        finally:
            kernel32.GlobalUnlock(handle)

    if not copy:
        raise PasteError("A clipboard object could not be copied.")
    return _ClipboardFormatCopy(format_id, kind, int(copy))


def _copy_clipboard_formats() -> list[_ClipboardFormatCopy]:
    """Deep-copy every transferable clipboard format by its storage type."""
    copied_formats: list[_ClipboardFormatCopy] = []
    _open_clipboard()
    try:
        format_id = 0
        while True:
            format_id = user32.EnumClipboardFormats(format_id)
            if not format_id:
                break
            copied_format = _copy_clipboard_format(format_id)
            if copied_format is not None:
                copied_formats.append(copied_format)
    except Exception:
        for copied_format in copied_formats:
            copied_format.release()
        raise
    finally:
        user32.CloseClipboard()
    return copied_formats


def _set_metafile_picture(value: tuple[int, int, int, int]) -> wintypes.HGLOBAL:
    """Allocate the outer ``METAFILEPICT`` block required by the clipboard."""
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(METAFILEPICT))
    if not handle:
        raise PasteError("Not enough memory is available for the clipboard.")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise PasteError("The clipboard memory could not be accessed.")
    try:
        ctypes.cast(pointer, ctypes.POINTER(METAFILEPICT)).contents = METAFILEPICT(
            *value
        )
    finally:
        kernel32.GlobalUnlock(handle)
    return handle


def _restore_copied_formats(
    copied_formats: list[_ClipboardFormatCopy],
) -> None:
    """Restore format copies and transfer their native handles to Windows."""
    _open_clipboard()
    try:
        if not user32.EmptyClipboard():
            raise PasteError("The clipboard could not be restored.")
        for copied_format in copied_formats:
            if copied_format.kind == "hglobal":
                assert isinstance(copied_format.value, bytes)
                _set_clipboard_data(copied_format.format_id, copied_format.value)
                continue

            if copied_format.kind == "metafile":
                assert isinstance(copied_format.value, tuple)
                handle = _set_metafile_picture(copied_format.value)
            else:
                assert isinstance(copied_format.value, int)
                handle = copied_format.value
            if not user32.SetClipboardData(copied_format.format_id, handle):
                if copied_format.kind == "metafile":
                    kernel32.GlobalFree(handle)
                raise PasteError("A clipboard object could not be restored.")
            # Windows owns both the outer handle and any contained GDI object now.
            copied_format.value = b""
    finally:
        user32.CloseClipboard()


def _set_clipboard_data(format_id: int, data: bytes) -> None:
    """Copy bytes into movable global memory and transfer it to Windows."""
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
            raise PasteError("The clipboard could not be cleared.")
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


def _replace_clipboard(text: str, marker: bytes) -> _ClipboardSnapshot:
    """Save the clipboard and replace it with marked snippet text."""
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
    """Send one balanced Ctrl+V key sequence to the foreground window."""
    def keyboard_input(key: int, flags: int = 0) -> INPUT:
        """Build one native keyboard event."""
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

    def __init__(
        self,
        snapshot: _ClipboardSnapshot,
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
        _send_ctrl_v()
    except Exception:
        pending.restore_clipboard()
        raise
    return pending
