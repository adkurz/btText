"""Windows-specific labels for portable keyboard shortcuts."""

import ctypes
import sys
from ctypes import create_unicode_buffer, windll, wintypes

from core.shortcuts import Hotkey


user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
)
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
user32.GetKeyboardLayout.restype = wintypes.HANDLE
user32.ActivateKeyboardLayout.argtypes = (wintypes.HANDLE, wintypes.UINT)
user32.ActivateKeyboardLayout.restype = wintypes.HANDLE


def get_key_label(hotkey: Hotkey) -> str:
    """Return the active-layout Windows label for a shortcut's main key."""
    if not hotkey.key.startswith("VK_"):
        return hotkey.key
    if sys.platform == "win32":
        scan_code = windll.user32.MapVirtualKeyW(
            hotkey.key_code,
            4,  # MAPVK_VK_TO_VSC_EX
        )
        key_data = (scan_code & 0xFF) << 16
        if scan_code & 0xFF00 in (0xE000, 0xE100):
            key_data |= 1 << 24
        buffer = create_unicode_buffer(64)
        if windll.user32.GetKeyNameTextW(key_data, buffer, 64):
            return buffer.value
    return hotkey.key


def get_foreground_keyboard_layout() -> int | None:
    """Return the keyboard layout used by the current foreground thread."""
    foreground_window = user32.GetForegroundWindow()
    if not foreground_window:
        return None
    thread_id = user32.GetWindowThreadProcessId(foreground_window, None)
    if not thread_id:
        return None
    keyboard_layout = user32.GetKeyboardLayout(thread_id)
    return int(keyboard_layout) if keyboard_layout else None


def activate_keyboard_layout(keyboard_layout: int) -> bool:
    """Activate a foreground thread's keyboard layout for the calling thread."""
    return bool(user32.ActivateKeyboardLayout(keyboard_layout, 0))
