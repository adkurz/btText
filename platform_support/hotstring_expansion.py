"""Replace typed hotstrings through a temporary Windows clipboard paste."""

from platform_support import keyboard_input, windows
from platform_support.clipboard import ClipboardError
from platform_support.clipboard_paste import PendingPaste


def expand_hotstring(
    target_window: int,
    text: str,
    hotstring_length: int,
    boundary_key: int | None,
) -> PendingPaste:
    """Replace a typed hotstring and optionally replay its boundary key."""
    if not windows.is_valid_window(target_window):
        raise ClipboardError("The active window no longer exists.")
    pending = PendingPaste.prepare(text)
    if not windows.activate_window(target_window):
        pending.restore_clipboard()
        raise ClipboardError("The active window could not be activated.")
    try:
        keyboard_input.send_virtual_key(0x08, hotstring_length)  # VK_BACK
        keyboard_input.send_ctrl_v()
        if boundary_key is not None:
            keyboard_input.send_virtual_key(boundary_key)
    except Exception:
        pending.restore_clipboard()
        raise
    return pending
