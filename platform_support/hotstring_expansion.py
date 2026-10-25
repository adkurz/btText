"""Replace typed hotstrings with temporary multi-format clipboard content."""

from collections.abc import Callable

from core.hotstrings import HotstringExpansionCancelled, HotstringExpansionError
from core.rich_text import ClipboardContent
from platform_support import keyboard_input, windows
from platform_support.clipboard import ClipboardError
from platform_support.clipboard_paste import (
    ClipboardPasteSession,
    PendingPaste,
    restore_after_failure,
)


def replay_suppressed_boundary(
    target: windows.WindowIdentity,
    boundary_key: keyboard_input.BoundaryInput,
    *,
    is_current: Callable[[], bool] | None = None,
) -> None:
    """Return a hook-suppressed boundary to its original target window."""
    _require_current(is_current)
    if not windows.matches_window_identity(target):
        raise HotstringExpansionError(
            "hotstring_target_window_missing",
            "The active window no longer exists.",
        )
    if not windows.activate_window_identity(target):
        raise HotstringExpansionError(
            "hotstring_target_window_activation_failed",
            "The active window could not be activated.",
        )
    _require_current(is_current)
    keyboard_input.send_boundary(boundary_key)


def _require_current(is_current: Callable[[], bool] | None) -> None:
    """Refuse stale work before activation, clipboard writes, or text deletion."""
    if is_current is not None and not is_current():
        raise HotstringExpansionCancelled


def expand_hotstring(
    target: windows.WindowIdentity,
    content: ClipboardContent | str,
    hotstring_length: int,
    boundary_key: keyboard_input.BoundaryInput | None,
    *,
    session: ClipboardPasteSession | None = None,
    is_current: Callable[[], bool] | None = None,
) -> PendingPaste:
    """Replace a typed hotstring and optionally replay its original boundary."""
    _require_current(is_current)
    if not windows.matches_window_identity(target):
        raise HotstringExpansionError(
            "hotstring_target_window_missing",
            "The active window no longer exists.",
        )
    pending = (
        session.prepare(content)
        if session is not None
        else PendingPaste.prepare(content)
    )
    try:
        _require_current(is_current)
        if not windows.activate_window_identity(target):
            raise HotstringExpansionError(
                "hotstring_target_window_activation_failed",
                "The active window could not be activated.",
            )
        _require_current(is_current)
        keyboard_input.send_hotstring_replacement(hotstring_length, boundary_key)
    except Exception as operation_error:
        restore_after_failure(pending.restore_clipboard, operation_error)
        raise
    return pending
