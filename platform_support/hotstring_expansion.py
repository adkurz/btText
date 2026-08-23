"""Replace typed hotstrings through a temporary Windows clipboard paste."""

from core.hotstrings import HotstringExpansionError
from platform_support import keyboard_input, windows
from platform_support.clipboard import ClipboardError
from platform_support.clipboard_paste import PendingPaste, restore_after_failure


def replay_suppressed_boundary(
    target: windows.WindowIdentity,
    boundary_key: int,
) -> None:
    """Return a hook-suppressed boundary key to its original target window."""
    if not windows.matches_window_identity(target):
        raise HotstringExpansionError(
            "hotstring_target_window_missing",
            "The active window no longer exists.",
        )
    if not windows.activate_window(target.handle):
        raise HotstringExpansionError(
            "hotstring_target_window_activation_failed",
            "The active window could not be activated.",
        )
    keyboard_input.send_virtual_key(boundary_key)


def expand_hotstring(
    target: windows.WindowIdentity,
    text: str,
    hotstring_length: int,
    boundary_key: int | None,
) -> PendingPaste:
    """Replace a typed hotstring and optionally replay its boundary key."""
    if not windows.matches_window_identity(target):
        raise HotstringExpansionError(
            "hotstring_target_window_missing",
            "The active window no longer exists.",
        )
    pending = PendingPaste.prepare(text)
    if not windows.activate_window(target.handle):
        operation_error = HotstringExpansionError(
            "hotstring_target_window_activation_failed",
            "The active window could not be activated.",
        )
        restore_after_failure(pending.restore_clipboard, operation_error)
        raise operation_error
    try:
        keyboard_input.send_virtual_key(0x08, hotstring_length)  # VK_BACK
        keyboard_input.send_ctrl_v()
        if boundary_key is not None:
            keyboard_input.send_virtual_key(boundary_key)
    except Exception as operation_error:
        restore_after_failure(pending.restore_clipboard, operation_error)
        raise
    return pending
