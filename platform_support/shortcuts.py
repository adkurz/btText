"""Windows-specific labels for portable keyboard shortcuts."""

import sys
from ctypes import create_unicode_buffer, windll

from core.shortcuts import Hotkey


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
