"""Interpret wxPython key events as portable global hotkeys."""

import wx

from core.shortcuts import Hotkey
from platform_support.shortcuts import is_windows_key_down


def key_name_from_code(key_code: int) -> str | None:
    """Map common wx key codes to stable serialized names."""
    if ord("A") <= key_code <= ord("Z"):
        return chr(key_code)
    if ord("0") <= key_code <= ord("9"):
        return chr(key_code)
    if wx.WXK_F1 <= key_code <= wx.WXK_F24:
        return "F{}".format(key_code - wx.WXK_F1 + 1)
    return None


def is_modifier_event(event: wx.KeyEvent) -> bool:
    """Return whether an event represents only a modifier key."""
    modifier_keys = {
        wx.WXK_CONTROL,
        wx.WXK_SHIFT,
        wx.WXK_ALT,
        getattr(wx, "WXK_RAW_CONTROL", wx.WXK_CONTROL),
        getattr(wx, "WXK_COMMAND", wx.WXK_CONTROL),
        getattr(wx, "WXK_WINDOWS_LEFT", wx.WXK_CONTROL),
        getattr(wx, "WXK_WINDOWS_RIGHT", wx.WXK_CONTROL),
    }
    # Windows uses separate virtual-key codes for left and right modifier keys
    # in raw keyboard events.
    raw_modifier_keys = {
        0xA0,  # VK_LSHIFT
        0xA1,  # VK_RSHIFT
        0xA2,  # VK_LCONTROL
        0xA3,  # VK_RCONTROL
        0xA4,  # VK_LMENU (Alt)
        0xA5,  # VK_RMENU (Alt/AltGr)
    }
    return (
        event.GetKeyCode() in modifier_keys
        or event.GetRawKeyCode() in raw_modifier_keys
    )


def key_name_from_event(event: wx.KeyEvent) -> str | None:
    """Derive a portable key name from a wx key event."""
    key_code = event.GetKeyCode()
    raw_key_code = event.GetRawKeyCode()

    try:
        return Hotkey.key_from_code(raw_key_code)
    except ValueError:
        pass

    # With Ctrl held down, wx can report letters as ASCII control codes
    # (Ctrl+A == 1 through Ctrl+Z == 26) instead of A through Z.
    if event.ControlDown() and 1 <= key_code <= 26:
        return chr(ord("A") + key_code - 1)

    key_name = key_name_from_code(key_code)
    if key_name is not None:
        return key_name

    unicode_key = event.GetUnicodeKey()
    if unicode_key != wx.WXK_NONE:
        key_name = key_name_from_code(unicode_key)
        if key_name is not None:
            return key_name

    # On Windows this is the virtual-key code and remains stable when Ctrl and
    # Alt transform GetKeyCode() into a control character.
    return key_name_from_code(raw_key_code)


def windows_modifier_down(event: wx.KeyEvent) -> bool:
    """Return whether wxPython or Windows reports a Windows modifier."""
    if event.MetaDown() or bool(event.GetModifiers() & wx.MOD_WIN):
        return True

    for key_name in ("WXK_WINDOWS_LEFT", "WXK_WINDOWS_RIGHT"):
        key_code = getattr(wx, key_name, None)
        if key_code is not None and wx.GetKeyState(key_code):
            return True

    return is_windows_key_down()


def hotkey_from_event(event: wx.KeyEvent) -> Hotkey:
    """Convert one non-modifier wx key event to a validated hotkey."""
    key_name = key_name_from_event(event)
    if key_name is None:
        raise ValueError("The pressed key is not supported")
    return Hotkey(
        key=key_name,
        control=event.ControlDown(),
        shift=event.ShiftDown(),
        alt=event.AltDown(),
        windows=windows_modifier_down(event),
    )
