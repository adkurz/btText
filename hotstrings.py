"""Windows low-level keyboard monitoring for snippet hotstrings."""

import ctypes
import string
import unicodedata
from ctypes import wintypes
from typing import Callable


WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
LLKHF_INJECTED = 0x10
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SPACE = 0x20
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    """Payload delivered to a ``WH_KEYBOARD_LL`` callback."""

    _fields_ = (
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)
user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.GetKeyboardState.argtypes = (ctypes.POINTER(ctypes.c_ubyte),)
user32.GetKeyboardState.restype = wintypes.BOOL
user32.ToUnicodeEx.argtypes = (
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_ubyte),
    wintypes.LPWSTR,
    ctypes.c_int,
    wintypes.UINT,
    wintypes.HKL,
)
user32.ToUnicodeEx.restype = ctypes.c_int
user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
user32.GetKeyboardLayout.restype = wintypes.HKL
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class HotstringMatcher:
    """Track typed text and recognize configured strings at boundaries."""

    def __init__(self):
        self._hotstrings: dict[str, object] = {}
        self._prefixes: set[str] = set()
        self._buffer = ""

    def update(self, snippets) -> None:
        """Replace the active case-insensitive hotstring mapping."""
        self._hotstrings = {
            snippet.hotstring.casefold(): snippet
            for snippet in snippets
            if snippet.hotstring
        }
        self._prefixes = {
            hotstring[:length]
            for hotstring in self._hotstrings
            for length in range(1, len(hotstring) + 1)
        }
        self.reset()

    def reset(self) -> None:
        """Discard all remembered user input."""
        self._buffer = ""

    def backspace(self) -> None:
        """Mirror one user-generated Backspace in the internal buffer."""
        self._buffer = self._buffer[:-1]

    def character(self, character: str):
        """Record a character or return a match when it is a boundary."""
        is_boundary = (
            character.isspace()
            or character in string.punctuation
            or unicodedata.category(character).startswith("P")
        )
        if is_boundary:
            snippet = self._hotstrings.get(self._buffer.casefold())
            if snippet is not None or character.isspace():
                self.reset()
                return snippet
            candidate = (self._buffer + character).casefold()
            if candidate not in self._prefixes:
                self.reset()
                return None
        # Keep enough recent word text for Backspace to reveal a valid trigger
        # again without allowing an unbounded buffer.
        self._buffer = (self._buffer + character)[-256:]
        return None


class KeyboardHook:
    """Install and own a process-wide Windows low-level keyboard hook."""

    def __init__(
        self,
        on_match: Callable[[object, int], bool],
        should_monitor: Callable[[], bool] = lambda: True,
    ):
        self._on_match = on_match
        self._should_monitor = should_monitor
        self._matcher = HotstringMatcher()
        self._handle = None
        self._foreground_window = None
        self._callback = HOOKPROC(self._hook_callback)

    def update(self, snippets) -> None:
        """Replace active hotstrings without reinstalling the hook."""
        self._matcher.update(snippets)

    def start(self) -> None:
        """Install the hook on the current desktop."""
        if self._handle:
            return
        module = kernel32.GetModuleHandleW(None)
        self._handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._callback, module, 0
        )
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def stop(self) -> None:
        """Remove the hook; repeated calls are harmless."""
        if self._handle:
            user32.UnhookWindowsHookEx(self._handle)
            self._handle = None
        self._matcher.reset()

    def _hook_callback(self, code, message, data):
        if code != HC_ACTION or message not in (WM_KEYDOWN, WM_SYSKEYDOWN):
            return user32.CallNextHookEx(self._handle, code, message, data)
        event = ctypes.cast(data, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if event.flags & LLKHF_INJECTED:
            return user32.CallNextHookEx(self._handle, code, message, data)
        foreground_window = user32.GetForegroundWindow()
        if foreground_window != self._foreground_window:
            self._foreground_window = foreground_window
            self._matcher.reset()
        if not self._should_monitor():
            self._matcher.reset()
            return user32.CallNextHookEx(self._handle, code, message, data)
        if event.vkCode == VK_BACK:
            self._matcher.backspace()
            return user32.CallNextHookEx(self._handle, code, message, data)
        if event.vkCode in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN):
            return user32.CallNextHookEx(self._handle, code, message, data)
        character = self._translate(event.vkCode, event.scanCode)
        if not character:
            self._matcher.reset()
            return user32.CallNextHookEx(self._handle, code, message, data)
        snippet = self._matcher.character(character)
        if snippet is not None and self._on_match(snippet, event.vkCode):
            return 1
        return user32.CallNextHookEx(self._handle, code, message, data)

    @staticmethod
    def _translate(virtual_key: int, scan_code: int) -> str | None:
        state = (ctypes.c_ubyte * 256)()
        if not user32.GetKeyboardState(state):
            return None
        buffer = ctypes.create_unicode_buffer(8)
        layout = user32.GetKeyboardLayout(0)
        count = user32.ToUnicodeEx(
            virtual_key, scan_code, state, buffer, len(buffer), 0, layout
        )
        return buffer.value[:count] if count == 1 else None
