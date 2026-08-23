"""Capture and restore independently owned Windows clipboard formats."""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import logging
import time

from platform_support.clipboard import (
    CF_UNICODETEXT,
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
ERROR_CLIPBOARD_FORMAT_NOT_AVAILABLE = 1418
CAPTURE_ATTEMPTS = 3
CAPTURE_RETRY_DELAY = 0.02

logger = logging.getLogger("bttext.clipboard")


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
user32.GetClipboardFormatNameW.argtypes = (
    wintypes.UINT,
    wintypes.LPWSTR,
    ctypes.c_int,
)
user32.GetClipboardFormatNameW.restype = ctypes.c_int


class _ClipboardFormatError(ClipboardError):
    """Identify one format that could not be copied from the clipboard."""

    def __init__(self, format_id: int, message: str, error_code: int = 0):
        """Retain non-content diagnostics for retry and logging."""
        self.format_id = format_id
        self.error_code = error_code
        super().__init__(message)


def _clipboard_format_name(format_id: int) -> str:
    """Return a diagnostic format name without reading clipboard contents."""
    standard_names = {
        CF_UNICODETEXT: "CF_UNICODETEXT",
        CF_BITMAP: "CF_BITMAP",
        CF_METAFILEPICT: "CF_METAFILEPICT",
        CF_PALETTE: "CF_PALETTE",
        CF_ENHMETAFILE: "CF_ENHMETAFILE",
        CF_OWNERDISPLAY: "CF_OWNERDISPLAY",
        CF_DSPBITMAP: "CF_DSPBITMAP",
        CF_DSPMETAFILEPICT: "CF_DSPMETAFILEPICT",
        CF_DSPENHMETAFILE: "CF_DSPENHMETAFILE",
    }
    if format_id in standard_names:
        return standard_names[format_id]
    buffer = ctypes.create_unicode_buffer(256)
    if user32.GetClipboardFormatNameW(format_id, buffer, len(buffer)):
        return "".join(
            character if character.isprintable() else "?"
            for character in buffer.value
        )
    return "unregistered"


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

    def duplicate(self) -> _ClipboardFormatCopy:
        """Create an independent copy for one clipboard-restore attempt."""
        if self.kind == "hglobal":
            assert isinstance(self.value, bytes)
            return _ClipboardFormatCopy(self.format_id, self.kind, self.value)
        if self.kind == "metafile":
            assert isinstance(self.value, tuple)
            metafile = gdi32.CopyMetaFileW(self.value[3], None)
            if not metafile:
                raise ClipboardError("A metafile could not be prepared for restore.")
            return _ClipboardFormatCopy(
                self.format_id,
                self.kind,
                (*self.value[:3], int(metafile)),
            )
        assert isinstance(self.value, int)
        if self.kind == "bitmap":
            value = user32.CopyImage(self.value, IMAGE_BITMAP, 0, 0, 0)
        elif self.kind == "palette":
            value = _copy_palette(self.value)
        elif self.kind == "enhmetafile":
            value = gdi32.CopyEnhMetaFileW(self.value, None)
        else:
            raise ClipboardError("An unsupported clipboard format cannot be restored.")
        if not value:
            raise ClipboardError("A clipboard object could not be prepared for restore.")
        return _ClipboardFormatCopy(self.format_id, self.kind, int(value))


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
        for attempt in range(CAPTURE_ATTEMPTS):
            try:
                return cls(_copy_clipboard_formats())
            except _ClipboardFormatError:
                if attempt + 1 == CAPTURE_ATTEMPTS:
                    break
                time.sleep(CAPTURE_RETRY_DELAY)
        return cls(_copy_clipboard_formats(skip_unavailable=True))

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
    ctypes.set_last_error(0)
    handle = user32.GetClipboardData(format_id)
    if not handle:
        # CF_OWNERDISPLAY deliberately has no transferable data handle.
        if format_id == CF_OWNERDISPLAY:
            return None
        error_code = ctypes.get_last_error()
        raise _ClipboardFormatError(
            format_id,
            "A clipboard format could not be read.",
            error_code or ERROR_CLIPBOARD_FORMAT_NOT_AVAILABLE,
        )

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
        ctypes.set_last_error(0)
        size = kernel32.GlobalSize(handle)
        if not size:
            raise _ClipboardFormatError(
                format_id,
                "A clipboard memory block could not be measured.",
                ctypes.get_last_error(),
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


def _copy_clipboard_formats(
    *,
    skip_unavailable: bool = False,
) -> list[_ClipboardFormatCopy]:
    """Deep-copy every transferable clipboard format by its storage type."""
    copied_formats: list[_ClipboardFormatCopy] = []
    skipped_formats: list[_ClipboardFormatError] = []
    _open_clipboard()
    try:
        format_id = 0
        while True:
            ctypes.set_last_error(0)
            format_id = user32.EnumClipboardFormats(format_id)
            if not format_id:
                error_code = ctypes.get_last_error()
                if error_code:
                    raise ClipboardError(
                        "The clipboard formats could not be enumerated "
                        f"(Windows error {error_code})."
                    )
                break
            try:
                copied_format = _copy_clipboard_format(format_id)
            except _ClipboardFormatError as error:
                if not skip_unavailable:
                    raise
                skipped_formats.append(error)
                logger.warning(
                    "Skipping unavailable clipboard format id=%d name=%s "
                    "windows_error=%d",
                    error.format_id,
                    _clipboard_format_name(error.format_id),
                    error.error_code,
                )
                continue
            if copied_format is not None:
                copied_formats.append(copied_format)
        if skipped_formats and not copied_formats:
            raise ClipboardError(
                "The available clipboard formats could not be preserved. "
                "Please copy plain text or clear the clipboard and try again."
            )
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
    """Restore formats through disposable copies so a failed attempt is retryable."""
    attempt_formats: list[_ClipboardFormatCopy] = []
    clipboard_open = False
    try:
        for copied_format in copied_formats:
            attempt_formats.append(copied_format.duplicate())
        _open_clipboard()
        clipboard_open = True
        if not user32.EmptyClipboard():
            raise ClipboardError("The clipboard could not be restored.")
        for copied_format in attempt_formats:
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
            # Windows owns both the outer handle and contained object now.
            copied_format.value = b""
    finally:
        for copied_format in attempt_formats:
            copied_format.release()
        if clipboard_open:
            user32.CloseClipboard()
