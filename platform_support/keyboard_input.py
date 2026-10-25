"""Send balanced keyboard input sequences through the Windows API."""

import ctypes
import secrets
from ctypes import wintypes

from platform_support.clipboard import ClipboardError, user32


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_EXTENDEDKEY = 0x0001
VK_CONTROL = 0x11
VK_LEFT = 0x25
VK_V = 0x56
INPUT_MARKER = secrets.randbits(ctypes.sizeof(ctypes.c_size_t) * 8) or 1

# Text boundaries retain the translated character; control boundaries retain
# their native key action (Space, Enter, or Tab).
BoundaryInput = int | str

_MODIFIER_KEYS = (
    0xA0, 0xA1,  # Left/right Shift.
    0xA2, 0xA3,  # Left/right Ctrl.
    0xA4, 0xA5,  # Left/right Alt, including AltGr.
)
_EXTENDED_MODIFIERS = frozenset((0xA3, 0xA5))


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
user32.GetAsyncKeyState.argtypes = (wintypes.INT,)
user32.GetAsyncKeyState.restype = wintypes.SHORT


def _keyboard_input(key: int, flags: int = 0) -> INPUT:
    """Build one native virtual-key input event."""
    value = INPUT()
    value.type = INPUT_KEYBOARD
    if key in _EXTENDED_MODIFIERS:
        flags |= KEYEVENTF_EXTENDEDKEY
    value.ki = KEYBDINPUT(key, 0, flags, 0, INPUT_MARKER)
    return value


def _send_inputs(values: list[INPUT], error_message: str) -> None:
    """Send exact chords without inheriting modifiers from the trigger key."""
    if not values:
        return
    held = [key for key in _MODIFIER_KEYS if user32.GetAsyncKeyState(key) & 0x8000]
    restore = [_keyboard_input(key) for key in held]
    # Release AltGr's Alt before Ctrl and restore Ctrl before Alt, keeping the
    # pair from becoming a standalone Alt release that could activate a menu.
    batch = [_keyboard_input(key, KEYEVENTF_KEYUP) for key in reversed(held)] + values + restore
    inputs = (INPUT * len(batch))(*batch)
    sent = user32.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT))
    if sent == len(inputs):
        return
    if sent:
        # A partial batch can leave synthetic Ctrl/V (or another key) down
        # and omit the final modifier restoration. Recover without replaying
        # deletion, paste, or boundary key-downs a second time.
        cleanup = []
        seen = set()
        for value in values:
            key = value.ki
            identity = (key.wVk, key.wScan, key.dwFlags)
            if key.dwFlags & KEYEVENTF_KEYUP or identity in seen:
                continue
            seen.add(identity)
            released = INPUT()
            released.type = INPUT_KEYBOARD
            released.ki = KEYBDINPUT(
                key.wVk, key.wScan, key.dwFlags | KEYEVENTF_KEYUP, 0, INPUT_MARKER,
            )
            cleanup.append(released)
        cleanup.extend(restore)
        recovery = (INPUT * len(cleanup))(*cleanup)
        user32.SendInput(len(recovery), recovery, ctypes.sizeof(INPUT))
    raise ClipboardError(error_message)


def send_ctrl_v() -> None:
    """Send one balanced Ctrl+V key sequence to the foreground window."""
    values = [
        _keyboard_input(VK_CONTROL),
        _keyboard_input(VK_V),
        _keyboard_input(VK_V, KEYEVENTF_KEYUP),
        _keyboard_input(VK_CONTROL, KEYEVENTF_KEYUP),
    ]
    _send_inputs(values, "The Ctrl+V keystroke could not be sent.")


def send_virtual_key(key: int, repetitions: int = 1) -> None:
    """Send balanced presses of one virtual key to the foreground window."""
    values = [
        _keyboard_input(key, flags)
        for _index in range(repetitions)
        for flags in (0, KEYEVENTF_KEYUP)
    ]
    _send_inputs(values, "A keyboard input could not be sent.")


def _boundary_inputs(boundary: BoundaryInput) -> list[INPUT]:
    """Encode a boundary without translating text through a later key state."""
    if isinstance(boundary, int):
        return [
            _keyboard_input(boundary),
            _keyboard_input(boundary, KEYEVENTF_KEYUP),
        ]
    if len(boundary) != 1:
        raise ValueError("A text boundary must contain exactly one character.")
    values = []
    encoded = boundary.encode("utf-16-le")
    for index in range(0, len(encoded), 2):
        code_unit = int.from_bytes(encoded[index:index + 2], "little")
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            value = INPUT()
            value.type = INPUT_KEYBOARD
            value.ki = KEYBDINPUT(0, code_unit, flags, 0, INPUT_MARKER)
            values.append(value)
    return values


def send_boundary(boundary: BoundaryInput) -> None:
    """Replay the original text character or native boundary key action."""
    values = _boundary_inputs(boundary)
    _send_inputs(values, "A keyboard input could not be sent.")


def send_hotstring_replacement(length: int, boundary_key: BoundaryInput | None) -> None:
    """Submit deletion, paste and boundary as one uninterrupted input batch."""
    if length < 0:
        raise ValueError("The hotstring length cannot be negative.")
    values = [
        _keyboard_input(0x08, flags)
        for _ in range(length)
        for flags in (0, KEYEVENTF_KEYUP)
    ]
    values.extend((
        _keyboard_input(VK_CONTROL),
        _keyboard_input(VK_V),
        _keyboard_input(VK_V, KEYEVENTF_KEYUP),
        _keyboard_input(VK_CONTROL, KEYEVENTF_KEYUP),
    ))
    if boundary_key is not None:
        values.extend(_boundary_inputs(boundary_key))
    _send_inputs(values, "A keyboard input could not be sent.")


def move_cursor_left(characters: int) -> None:
    """Move the foreground text caret left by ``characters`` positions."""
    if characters < 0:
        raise ValueError("The cursor movement cannot be negative.")
    if characters:
        send_virtual_key(VK_LEFT, characters)
