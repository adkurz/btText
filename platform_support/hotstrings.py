"""Windows low-level keyboard monitoring for snippet hotstrings."""

import ctypes
import logging
import threading
import time
from collections.abc import Mapping
from ctypes import wintypes
from typing import Callable

from core.hotstrings import HotstringMatcher


WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_TIMER = 0x0113
WM_QUIT = 0x0012
HOOK_THREAD_SHUTDOWN_TIMEOUT_SECONDS = 2
HOOK_HEALTH_CHECK_INTERVAL_MS = 500
HOOK_REFRESH_INTERVAL_SECONDS = 60
HOOK_REFRESH_IDLE_SECONDS = 1
LLKHF_INJECTED = 0x10
LLKHF_ALTDOWN = 0x20
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SPACE = 0x20
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5

SHIFT_KEYS = frozenset((VK_SHIFT, VK_LSHIFT, VK_RSHIFT))
CONTROL_KEYS = frozenset((VK_CONTROL, VK_LCONTROL, VK_RCONTROL))
ALT_KEYS = frozenset((VK_MENU, VK_LMENU, VK_RMENU))
WINDOWS_KEYS = frozenset((VK_LWIN, VK_RWIN))
NON_SHIFT_MODIFIER_KEYS = CONTROL_KEYS | ALT_KEYS | WINDOWS_KEYS
MODIFIER_KEYS = SHIFT_KEYS | NON_SHIFT_MODIFIER_KEYS

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


class GUITHREADINFO(ctypes.Structure):
    """Focus information for the foreground GUI thread."""

    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    )


class LASTINPUTINFO(ctypes.Structure):
    """Timestamp of the most recent user input in the current session."""

    _fields_ = (
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
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
user32.GetAsyncKeyState.argtypes = (wintypes.INT,)
user32.GetAsyncKeyState.restype = wintypes.SHORT
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
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
)
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetGUIThreadInfo.argtypes = (
    wintypes.DWORD,
    ctypes.POINTER(GUITHREADINFO),
)
user32.GetGUIThreadInfo.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.GetMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
)
user32.GetMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.SetTimer.argtypes = (
    wintypes.HWND,
    ctypes.c_size_t,
    wintypes.UINT,
    wintypes.LPVOID,
)
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = (wintypes.HWND, ctypes.c_size_t)
user32.KillTimer.restype = wintypes.BOOL
user32.GetLastInputInfo.argtypes = (ctypes.POINTER(LASTINPUTINFO),)
user32.GetLastInputInfo.restype = wintypes.BOOL
kernel32.GetTickCount64.restype = ctypes.c_ulonglong


logger = logging.getLogger("bttext.hotstrings")


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
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._timer_id: int | None = None
        self._hook_installed_at = 0.0
        self._observed_foreground_window: int | None = None
        self._startup_complete = threading.Event()
        self._startup_error: OSError | None = None
        self._state_lock = threading.Lock()
        self._input_context: (
            tuple[int | None, int | None, int | None] | None
        ) = None
        self._callback = HOOKPROC(self._hook_callback)

    def update(self, hotstrings: Mapping[str, object]) -> None:
        """Replace active hotstrings without reinstalling the hook."""
        with self._state_lock:
            self._matcher.update(hotstrings)

    def start(self) -> None:
        """Install the hook on a dedicated message-loop thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._startup_complete.clear()
        self._startup_error = None
        self._thread = threading.Thread(
            target=self._run_message_loop,
            name="btText hotstring hook",
            daemon=True,
        )
        self._thread.start()
        self._startup_complete.wait()
        if self._startup_error is not None:
            error = self._startup_error
            self._thread.join()
            self._thread = None
            raise error

    def stop(self) -> None:
        """Remove the hook; repeated calls are harmless."""
        thread = self._thread
        thread_id = self._thread_id
        if thread is not None and thread.is_alive() and thread_id is not None:
            if not user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0):
                logger.warning("Could not request hotstring hook shutdown")
            thread.join(HOOK_THREAD_SHUTDOWN_TIMEOUT_SECONDS)
            if thread.is_alive():
                logger.warning("Hotstring hook thread did not stop in time")
                return
        self._thread = None
        with self._state_lock:
            self._matcher.reset()

    def _run_message_loop(self) -> None:
        """Own the native hook and pump its thread message queue."""
        try:
            self._thread_id = int(kernel32.GetCurrentThreadId())
            self._handle = self._install_native_hook()
            self._hook_installed_at = time.monotonic()
            self._observed_foreground_window = self._get_foreground_window()
            self._timer_id = int(
                user32.SetTimer(
                    None,
                    0,
                    HOOK_HEALTH_CHECK_INTERVAL_MS,
                    None,
                )
            )
            if not self._timer_id:
                raise ctypes.WinError(ctypes.get_last_error())
        except Exception as error:
            if self._handle:
                user32.UnhookWindowsHookEx(self._handle)
                self._handle = None
            self._startup_error = (
                error if isinstance(error, OSError) else OSError(str(error))
            )
            self._thread_id = None
            self._startup_complete.set()
            return
        logger.info("Hotstring keyboard hook started")
        self._startup_complete.set()
        message = wintypes.MSG()
        try:
            while True:
                result = user32.GetMessageW(
                    ctypes.byref(message),
                    None,
                    0,
                    0,
                )
                if result == 0:
                    break
                if result == -1:
                    logger.error("Hotstring hook message loop failed")
                    break
                if message.message == WM_TIMER and message.wParam == self._timer_id:
                    self._monitor_hook()
        finally:
            if self._timer_id and not user32.KillTimer(None, self._timer_id):
                logger.warning("Could not remove hotstring hook health timer")
            self._timer_id = None
            if self._handle and not user32.UnhookWindowsHookEx(self._handle):
                logger.warning("Could not remove hotstring keyboard hook")
            self._handle = None
            self._thread_id = None
            logger.info("Hotstring keyboard hook stopped")

    def _install_native_hook(self):
        """Install one native hook or raise the corresponding Windows error."""
        module = kernel32.GetModuleHandleW(None)
        handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._callback, module, 0
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def _monitor_hook(self) -> None:
        """Renew the hook after window changes or when it has aged."""
        foreground = self._get_foreground_window()
        foreground_changed = foreground != self._observed_foreground_window
        self._observed_foreground_window = foreground
        age = time.monotonic() - self._hook_installed_at
        periodic_refresh_due = (
            age >= HOOK_REFRESH_INTERVAL_SECONDS
            and self._is_user_input_idle()
        )
        if not foreground_changed and not periodic_refresh_due:
            return
        reason = "foreground window changed" if foreground_changed else "scheduled"
        try:
            replacement = self._install_native_hook()
        except OSError:
            logger.exception(
                "Could not refresh hotstring keyboard hook (%s)", reason
            )
            return
        previous = self._handle
        self._handle = replacement
        self._hook_installed_at = time.monotonic()
        if previous and not user32.UnhookWindowsHookEx(previous):
            logger.warning("Could not remove replaced hotstring keyboard hook")
        logger.info("Hotstring keyboard hook refreshed (%s)", reason)

    @staticmethod
    def _get_foreground_window() -> int | None:
        """Return the current foreground handle for health monitoring."""
        foreground = user32.GetForegroundWindow()
        return int(foreground) if foreground else None

    @staticmethod
    def _is_user_input_idle() -> bool:
        """Return whether recent input has settled enough for hook renewal."""
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            logger.warning("Could not query user input idle time")
            return False
        elapsed_ms = int(kernel32.GetTickCount64()) - int(info.dwTime)
        return elapsed_ms >= HOOK_REFRESH_IDLE_SECONDS * 1_000

    def _hook_callback(self, code, message, data):
        """Contain callback failures so ctypes never unwinds into Windows."""
        try:
            return self._process_hook_event(code, message, data)
        except Exception:
            logger.exception("Hotstring keyboard hook callback failed")
            return user32.CallNextHookEx(self._handle, code, message, data)

    def _process_hook_event(self, code, message, data):
        """Pass modifiers through immediately and serialize text processing."""
        keyboard_messages = (
            WM_KEYDOWN,
            WM_KEYUP,
            WM_SYSKEYDOWN,
            WM_SYSKEYUP,
        )
        if code != HC_ACTION or message not in keyboard_messages:
            return user32.CallNextHookEx(self._handle, code, message, data)
        event = ctypes.cast(data, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        if event.flags & LLKHF_INJECTED or event.vkCode in MODIFIER_KEYS:
            # A low-level hook must never delay or consume a modifier. In
            # particular, Alt arrives as a system-key message and Windows
            # cannot activate menus or Alt-based shortcuts until it returns.
            return user32.CallNextHookEx(self._handle, code, message, data)
        with self._state_lock:
            return self._process_hook_event_locked(message, event, data)

    def _process_hook_event_locked(self, message, event, data):
        """Process an event while matcher state is protected."""
        if message in (WM_KEYUP, WM_SYSKEYUP):
            return user32.CallNextHookEx(
                self._handle, HC_ACTION, message, data
            )
        input_context = self._get_input_context()
        if input_context != self._input_context:
            self._input_context = input_context
            self._matcher.reset()
        if not self._should_monitor():
            self._matcher.reset()
            return user32.CallNextHookEx(
                self._handle, HC_ACTION, message, data
            )
        altgr_down = self._is_altgr_down(event.flags)
        if self._has_non_text_modifier_chord(event.flags, altgr_down):
            # A shortcut does not insert its ordinary key into the target.
            # Discard partial input instead of feeding control characters or
            # layout-dependent translations into the hotstring matcher.
            self._matcher.reset()
            return user32.CallNextHookEx(
                self._handle, HC_ACTION, message, data
            )
        if event.vkCode == VK_BACK:
            self._matcher.backspace()
            return user32.CallNextHookEx(
                self._handle, HC_ACTION, message, data
            )
        character = self._translate(
            event.vkCode,
            event.scanCode,
            shift_down=self._is_key_down(SHIFT_KEYS),
            altgr_down=altgr_down,
            keyboard_layout=input_context[2],
        )
        if not character:
            self._matcher.reset()
            return user32.CallNextHookEx(
                self._handle, HC_ACTION, message, data
            )
        snippet = self._matcher.character(character)
        if snippet is not None and self._on_match(snippet, event.vkCode):
            return 1
        return user32.CallNextHookEx(self._handle, HC_ACTION, message, data)

    @staticmethod
    def _is_key_down(virtual_keys: frozenset[int]) -> bool:
        """Return whether any key in one modifier family is physically down."""
        return any(user32.GetAsyncKeyState(key) & 0x8000 for key in virtual_keys)

    @classmethod
    def _is_altgr_down(cls, event_flags: int) -> bool:
        """Return whether the current key is typed through Windows AltGr."""
        return bool(
            event_flags & LLKHF_ALTDOWN
            and cls._is_key_down(CONTROL_KEYS)
            and cls._is_key_down(frozenset((VK_RMENU,)))
        )

    @classmethod
    def _has_non_text_modifier_chord(
        cls,
        event_flags: int,
        altgr_down: bool,
    ) -> bool:
        """Return whether the current ordinary key belongs to a shortcut."""
        if cls._is_key_down(WINDOWS_KEYS):
            return True
        control_down = cls._is_key_down(CONTROL_KEYS)
        alt_down = bool(event_flags & LLKHF_ALTDOWN) or cls._is_key_down(ALT_KEYS)
        return (control_down or alt_down) and not altgr_down

    @staticmethod
    def _get_input_context() -> tuple[int | None, int | None, int | None]:
        """Identify foreground, focused child, and active keyboard layout."""
        foreground = user32.GetForegroundWindow()
        if not foreground:
            return None, None, None
        thread_id = user32.GetWindowThreadProcessId(foreground, None)
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(info)
        focused = None
        if thread_id and user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            focused = int(info.hwndFocus) if info.hwndFocus else None
        keyboard_layout = (
            int(user32.GetKeyboardLayout(thread_id)) if thread_id else None
        )
        return int(foreground), focused, keyboard_layout

    @staticmethod
    def _translate(
        virtual_key: int,
        scan_code: int,
        shift_down: bool = False,
        altgr_down: bool = False,
        keyboard_layout: int | None = None,
    ) -> str | None:
        state = (ctypes.c_ubyte * 256)()
        if not user32.GetKeyboardState(state):
            return None
        # The asynchronous keyboard state is not guaranteed to have been
        # updated when a low-level hook runs. Use the state observed directly
        # from Shift key-down/key-up events instead.
        shift_state = 0x80 if shift_down else 0
        state[VK_SHIFT] = shift_state
        state[VK_LSHIFT] = shift_state
        state[VK_RSHIFT] = shift_state
        for modifier_key in CONTROL_KEYS | ALT_KEYS:
            state[modifier_key] &= 0x7F
        if altgr_down:
            # Low-level hook callbacks can run before GetKeyboardState reflects
            # the event. Supply the canonical Ctrl+right-Alt AltGr state.
            state[VK_CONTROL] = 0x80
            state[VK_LCONTROL] = 0x80
            state[VK_MENU] = 0x80
            state[VK_RMENU] = 0x80
        buffer = ctypes.create_unicode_buffer(8)
        layout = keyboard_layout or user32.GetKeyboardLayout(0)
        count = user32.ToUnicodeEx(
            virtual_key, scan_code, state, buffer, len(buffer), 0, layout
        )
        return buffer.value[:count] if count == 1 else None
