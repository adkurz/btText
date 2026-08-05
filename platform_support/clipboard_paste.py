"""Paste snippet text into another Windows application via the clipboard."""

from __future__ import annotations

from collections.abc import Callable
import ctypes
import uuid

from platform_support import keyboard_input, windows
from platform_support.clipboard import (
    CF_UNICODETEXT,
    ClipboardError,
    _exclude_current_item_from_history_and_cloud,
    _open_clipboard,
    _set_clipboard_data,
    _set_clipboard_text,
    kernel32,
    user32,
)
from platform_support.clipboard_snapshot import ClipboardSnapshot


PasteError = ClipboardError


class ClipboardRestoreError(ClipboardError):
    """Report an operation failure followed by failed clipboard recovery."""

    def __init__(
        self,
        operation_error: Exception,
        restore_error: Exception,
    ):
        """Retain both failures while presenting one clipboard error."""
        self.operation_error = operation_error
        self.restore_error = restore_error
        super().__init__(
            "{operation_error} The previous clipboard contents could not be "
            "restored: {restore_error}".format(
                operation_error=operation_error,
                restore_error=restore_error,
            )
        )


def restore_after_failure(
    restore: Callable[[], None],
    operation_error: Exception,
) -> None:
    """Attempt recovery and preserve both errors when recovery also fails."""
    try:
        restore()
    except Exception as restore_error:
        raise ClipboardRestoreError(
            operation_error,
            restore_error,
        ) from operation_error


_MARKER_FORMAT = user32.RegisterClipboardFormatW("BTText.PasteMarker")
if not _MARKER_FORMAT:
    raise ctypes.WinError(ctypes.get_last_error())


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
            _exclude_current_item_from_history_and_cloud()
        finally:
            user32.CloseClipboard()
        return snapshot
    except Exception as operation_error:
        # EmptyClipboard may already have discarded the original contents.
        restore_after_failure(snapshot.restore, operation_error)
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

    @classmethod
    def prepare(cls, text: str) -> PendingPaste:
        """Replace the clipboard with marked text and retain its snapshot."""
        marker = uuid.uuid4().bytes
        return cls(_replace_clipboard(text, marker), marker, text)

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
    if not windows.is_valid_window(target_window):
        raise PasteError("The previously active window no longer exists.")

    pending = PendingPaste.prepare(text)
    if not windows.activate_window(target_window):
        operation_error = PasteError(
            "The previously active window could not be activated."
        )
        restore_after_failure(pending.restore_clipboard, operation_error)
        raise operation_error
    try:
        keyboard_input.send_ctrl_v()
    except Exception as operation_error:
        restore_after_failure(pending.restore_clipboard, operation_error)
        raise
    return pending
