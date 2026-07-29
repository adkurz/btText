"""Capture and restore independently owned Windows clipboard formats."""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from platform_support.clipboard import (
    GMEM_MOVEABLE,
    ClipboardError,
    _open_clipboard,
    _set_clipboard_data,
    kernel32,
    user32,
)


CF_BITMAP = 2
CF_METAFILEPICT = 3
CF_PALETTE = 9
CF_ENHMETAFILE = 14
CF_OWNERDISPLAY = 0x0080
CF_DSPBITMAP = 0x0082
CF_DSPMETAFILEPICT = 0x0083
CF_DSPENHMETAFILE = 0x008E
IMAGE_BITMAP = 0


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
        raise ClipboardError("A palette on the clipboard could not be read.")
    # LOGPALETTE is two WORDs followed by PALETTEENTRY[palNumEntries].
    buffer = ctypes.create_string_buffer(4 + entry_count * 4)
    header = ctypes.cast(buffer, ctypes.POINTER(wintypes.WORD))
    header[0] = 0x0300
    header[1] = entry_count
    entries = ctypes.byref(buffer, 4)
    if gdi32.GetPaletteEntries(handle, 0, entry_count, entries) != entry_count:
        raise ClipboardError("A palette on the clipboard could not be copied.")
    copy = gdi32.CreatePalette(buffer)
    if not copy:
        raise ClipboardError("A palette on the clipboard could not be copied.")
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


class ClipboardSnapshot:
    """Independent copies of all materialized Windows clipboard formats."""

    def __init__(
        self,
        copied_formats: list[_ClipboardFormatCopy],
    ):
        """Own copied formats until they are restored or explicitly discarded."""
        self._copied_formats = copied_formats
        self._closed = False

    @classmethod
    def capture(cls) -> ClipboardSnapshot:
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


def _copy_clipboard_format(format_id: int) -> _ClipboardFormatCopy | None:
    """Copy one format according to the ownership rules of its storage type."""
    handle = user32.GetClipboardData(format_id)
    if not handle:
        # CF_OWNERDISPLAY deliberately has no transferable data handle.
        if format_id == CF_OWNERDISPLAY:
            return None
        raise ClipboardError("A clipboard format could not be read.")

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
            raise ClipboardError(
                "A metafile on the clipboard could not be accessed."
            )
        try:
            source = ctypes.cast(pointer, ctypes.POINTER(METAFILEPICT)).contents
            metafile = gdi32.CopyMetaFileW(source.hMF, None)
            if not metafile:
                raise ClipboardError(
                    "A metafile on the clipboard could not be copied."
                )
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
            raise ClipboardError(
                "A clipboard memory block could not be measured."
            )
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise ClipboardError(
                "A clipboard memory block could not be accessed."
            )
        try:
            return _ClipboardFormatCopy(
                format_id,
                "hglobal",
                ctypes.string_at(pointer, size),
            )
        finally:
            kernel32.GlobalUnlock(handle)

    if not copy:
        raise ClipboardError("A clipboard object could not be copied.")
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
        raise ClipboardError("Not enough memory is available for the clipboard.")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise ClipboardError("The clipboard memory could not be accessed.")
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
            raise ClipboardError("The clipboard could not be restored.")
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
                raise ClipboardError("A clipboard object could not be restored.")
            # Windows owns both the outer handle and any contained GDI object now.
            copied_format.value = b""
    finally:
        user32.CloseClipboard()
