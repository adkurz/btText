"""Send balanced virtual-key input sequences through the Windows API."""

import ctypes
from ctypes import wintypes

from platform_support.clipboard import ClipboardError, user32


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56


class KEYBDINPUT(ctypes.Structure):
    """Windows keyboard-input payload used by ``SendInput``."""

    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class MOUSEINPUT(ctypes.Structure):
    """Windows mouse-input payload required by the ``INPUT`` union."""

    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class HARDWAREINPUT(ctypes.Structure):
    """Windows hardware-input payload required by the ``INPUT`` union."""

    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    """Union of the native input payload variants."""

    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    """Native input event passed to the Windows ``SendInput`` API."""

    _anonymous_ = ("data",)
    _fields_ = (("type", wintypes.DWORD), ("data", _INPUTUNION))


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _keyboard_input(key: int, flags: int = 0) -> INPUT:
    """Build one native virtual-key input event."""
    value = INPUT()
    value.type = INPUT_KEYBOARD
    value.ki = KEYBDINPUT(key, 0, flags, 0, 0)
    return value


def send_ctrl_v() -> None:
    """Send one balanced Ctrl+V key sequence to the foreground window."""
    inputs = (INPUT * 4)(
        _keyboard_input(VK_CONTROL),
        _keyboard_input(VK_V),
        _keyboard_input(VK_V, KEYEVENTF_KEYUP),
        _keyboard_input(VK_CONTROL, KEYEVENTF_KEYUP),
    )
    if user32.SendInput(
        len(inputs),
        inputs,
        ctypes.sizeof(INPUT),
    ) != len(inputs):
        raise ClipboardError("The Ctrl+V keystroke could not be sent.")


def send_virtual_key(key: int, repetitions: int = 1) -> None:
    """Send balanced presses of one virtual key to the foreground window."""
    values = [
        _keyboard_input(key, flags)
        for _index in range(repetitions)
        for flags in (0, KEYEVENTF_KEYUP)
    ]
    inputs = (INPUT * len(values))(*values)
    if user32.SendInput(
        len(inputs),
        inputs,
        ctypes.sizeof(INPUT),
    ) != len(inputs):
        raise ClipboardError("A keyboard input could not be sent.")
