"""Copy Unicode text to the Windows clipboard with privacy controls."""

import ctypes
import time
from ctypes import wintypes

from core.rich_text import ClipboardContent

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
_CLOUD_CLIPBOARD_FORMAT = user32.RegisterClipboardFormatW("CanUploadToCloudClipboard")
if not _CLOUD_CLIPBOARD_FORMAT:
    raise ctypes.WinError(ctypes.get_last_error())
_HTML_FORMAT = user32.RegisterClipboardFormatW("HTML Format")
if not _HTML_FORMAT:
    raise ctypes.WinError(ctypes.get_last_error())


def _exclude_current_item_from_history_and_cloud() -> None:
    """Keep the open clipboard's current item out of Windows storage."""
    disabled = b"\0\0\0\0"
    _set_clipboard_data(_CLIPBOARD_HISTORY_FORMAT, disabled)
    _set_clipboard_data(_CLOUD_CLIPBOARD_FORMAT, disabled)


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


def _encode_cf_html(fragment: str) -> bytes:
    """Encode an HTML fragment using the byte offsets required by CF_HTML."""
    prefix = "<html><body><!--StartFragment-->"
    suffix = "<!--EndFragment--></body></html>"
    html = (prefix + fragment + suffix).encode("utf-8")
    header_template = (
        "Version:1.0\r\n"
        "StartHTML:{start_html:010d}\r\n"
        "EndHTML:{end_html:010d}\r\n"
        "StartFragment:{start_fragment:010d}\r\n"
        "EndFragment:{end_fragment:010d}\r\n"
    )
    placeholder_header = header_template.format(
        start_html=0,
        end_html=0,
        start_fragment=0,
        end_fragment=0,
    ).encode("ascii")
    start_html = len(placeholder_header)
    start_fragment = start_html + len(prefix.encode("utf-8"))
    end_fragment = start_fragment + len(fragment.encode("utf-8"))
    end_html = start_html + len(html)
    header = header_template.format(
        start_html=start_html,
        end_html=end_html,
        start_fragment=start_fragment,
        end_fragment=end_fragment,
    ).encode("ascii")
    return header + html + b"\0"


def _set_clipboard_content(content: ClipboardContent) -> None:
    """Write every representation of one item while the clipboard is open."""
    _set_clipboard_text(content.plain_text)
    if content.html is not None:
        _set_clipboard_data(_HTML_FORMAT, _encode_cf_html(content.html))


def _read_open_clipboard_text() -> str | None:
    """Read Unicode text while the caller owns the open clipboard."""
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    handle = user32.GetClipboardData(CF_UNICODETEXT)
    if not handle:
        raise ClipboardError("The clipboard text could not be accessed.")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        raise ClipboardError("The clipboard text could not be accessed.")
    try:
        data = ctypes.string_at(pointer, kernel32.GlobalSize(handle))
    finally:
        kernel32.GlobalUnlock(handle)
    try:
        return data.decode("utf-16-le").split("\0", 1)[0]
    except UnicodeDecodeError as error:
        raise ClipboardError("The clipboard text is not valid Unicode.") from error


def read_text() -> str | None:
    """Return current Unicode clipboard text without changing the clipboard."""
    _open_clipboard()
    try:
        return _read_open_clipboard_text()
    finally:
        user32.CloseClipboard()


def copy_text(
    text: str,
    include_in_history: bool = True,
    allow_cloud_upload: bool = True,
) -> None:
    """Copy text with independent history and cloud-upload controls."""
    copy_content(
        ClipboardContent(text),
        include_in_history=include_in_history,
        allow_cloud_upload=allow_cloud_upload,
    )


def copy_content(
    content: ClipboardContent,
    include_in_history: bool = True,
    allow_cloud_upload: bool = True,
) -> None:
    """Copy plain text and optional HTML with independent privacy controls."""
    _open_clipboard()
    try:
        if not user32.EmptyClipboard():
            raise ClipboardError("The clipboard could not be cleared.")
        _set_clipboard_content(content)
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
