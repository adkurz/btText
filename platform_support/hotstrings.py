"""Windows low-level keyboard monitoring for snippet hotstrings."""

import ctypes
import logging
import os
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Callable

from core.hotstrings import HotstringMatcher
from platform_support import keyboard_input, windows


WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_TIMER = 0x0113
WM_QUIT = 0x0012
MOUSE_ACTION_MESSAGES = frozenset((
    0x0201, 0x0202, 0x0204, 0x0205,  # Left/right button down and up.
    0x0207, 0x0208, 0x020B, 0x020C,  # Middle/X button down and up.
    0x020A, 0x020E,  # Vertical and horizontal wheel.
))
HOOK_THREAD_SHUTDOWN_TIMEOUT_SECONDS = 2
HOOK_HEALTH_CHECK_INTERVAL_MS = 500
HOOK_REFRESH_INTERVAL_SECONDS = 60
HOOK_REFRESH_IDLE_SECONDS = 1
TARGET_FOCUS_RESTORE_TIMEOUT_SECONDS = 0.2
TARGET_FOCUS_RESTORE_POLL_SECONDS = 0.01
LLKHF_INJECTED = 0x10
LLKHF_ALTDOWN = 0x20
TO_UNICODE_NO_STATE_CHANGE = 0x04
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


class MSLLHOOKSTRUCT(ctypes.Structure):
    """Payload delivered to a low-level mouse callback."""

    _fields_ = (
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


@dataclass(frozen=True)
class InputCheckpoint:
    """Bind queued work to its target and track interactive input ownership."""

    context: tuple[int | None, int | None, int | None]
    cancelled: threading.Event = field(default_factory=threading.Event)
    interactive: threading.Event = field(default_factory=threading.Event)


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
user32.WindowFromPoint.argtypes = (wintypes.POINT,)
user32.WindowFromPoint.restype = wintypes.HWND
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
        on_match: Callable[[object, keyboard_input.BoundaryInput, InputCheckpoint], bool],
        should_monitor: Callable[[], bool] = lambda: True,
    ):
        self._on_match = on_match
        self._should_monitor = should_monitor
        self._matcher = HotstringMatcher()
        self._handle = None
        self._mouse_handle = None
        self._pending_checkpoint: InputCheckpoint | None = None
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
        self._mouse_callback_ref = HOOKPROC(self._mouse_callback)

    def _cancel_pending(self, *, input_changed: bool = False) -> None:
        """Cancel lifecycle changes; observe input only outside a prompt."""
        checkpoint = self._pending_checkpoint
        if checkpoint is not None and not (
            input_changed and checkpoint.interactive.is_set()
        ):
            checkpoint.cancelled.set()

    @contextmanager
    def expansion(self, checkpoint: InputCheckpoint) -> Iterator[None]:
        """Retain an interactive target until activation and insertion finish."""
        try:
            yield
        finally:
            checkpoint.interactive.clear()

    def begin_input(self, checkpoint: InputCheckpoint) -> None:
        """Let the input dialog own its target across arbitrary user activity.

        Confirmation authorizes returning to the captured window. There is no
        time limit or dependency on the intervening foreground, child focus,
        or keyboard layout. Model updates and shutdown can still cancel it.
        """
        checkpoint.interactive.set()

    def is_current(
        self,
        checkpoint: InputCheckpoint,
        *,
        allow_own_foreground: bool = False,
    ) -> bool:
        """Recheck the target and compare child focus when it is available."""
        if checkpoint.cancelled.is_set() or checkpoint.context[0] is None:
            return False
        if checkpoint.interactive.is_set():
            # Before activation, any foreground is allowed after a dialog.
            # Immediately before sending keys the caller uses the strict form.
            return allow_own_foreground or (
                self._get_foreground_window() == checkpoint.context[0]
            )
        deadline = time.monotonic() + TARGET_FOCUS_RESTORE_TIMEOUT_SECONDS
        while not checkpoint.cancelled.is_set():
            foreground = self._get_foreground_window()
            if foreground != checkpoint.context[0]:
                identity = windows.get_window_identity(foreground)
                if (
                    allow_own_foreground
                    and identity is not None
                    and identity.process_id == os.getpid()
                ):
                    # The target's focus is unavailable while our prompt is
                    # active. Expansion/replay rechecks after activation.
                    return not checkpoint.cancelled.is_set()
                break
            context = self._get_input_context(checkpoint.context[0])
            if context[0] != checkpoint.context[0] or context[2] != checkpoint.context[2]:
                break
            original_focus = checkpoint.context[1]
            current_focus = context[1]
            if original_focus is None or current_focus == original_focus:
                return not checkpoint.cancelled.is_set()
            if current_focus is not None:
                break
            if not allow_own_foreground or time.monotonic() >= deadline:
                # Some applications expose no child focus. Window identity
                # (checked by expansion/replay) and observed input still guard
                # the replacement; missing focus alone must not disable it.
                return not checkpoint.cancelled.is_set()
            # Closing a modal prompt can activate the target before its GUI
            # thread restores child focus (notably in Notepad++). Wait only
            # briefly for comparable focus; a different child/layout cancels.
            # The native hook thread keeps observing intervening user input.
            time.sleep(TARGET_FOCUS_RESTORE_POLL_SECONDS)
        checkpoint.cancelled.set()
        return False

    def update(self, hotstrings: Mapping[str, object]) -> None:
        """Replace active hotstrings without reinstalling the hook."""
        self._cancel_pending()
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
        self._cancel_pending()
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
            self._mouse_handle = self._install_mouse_hook()
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
            if self._mouse_handle:
                user32.UnhookWindowsHookEx(self._mouse_handle)
                self._mouse_handle = None
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
            self._cancel_pending()
            if self._timer_id and not user32.KillTimer(None, self._timer_id):
                logger.warning("Could not remove hotstring hook health timer")
            self._timer_id = None
            if self._handle and not user32.UnhookWindowsHookEx(self._handle):
                logger.warning("Could not remove hotstring keyboard hook")
            self._handle = None
            if self._mouse_handle and not user32.UnhookWindowsHookEx(self._mouse_handle):
                logger.warning("Could not remove hotstring mouse observer")
            self._mouse_handle = None
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

    def _install_mouse_hook(self):
        """Observe caret-changing mouse actions without consuming them."""
        handle = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_callback_ref,
            kernel32.GetModuleHandleW(None), 0,
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def _mouse_callback(self, code, message, data):
        """Invalidate clicks/wheels unless an input dialog owns the target."""
        try:
            if code == HC_ACTION and message in MOUSE_ACTION_MESSAGES:
                event = ctypes.cast(data, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                handle = user32.WindowFromPoint(event.pt)
                identity = windows.get_window_identity(handle)
                if identity is None or identity.process_id != os.getpid():
                    self._cancel_pending(input_changed=True)
                    with self._state_lock:
                        self._matcher.reset()
        except Exception:
            self._cancel_pending(input_changed=True)
            logger.exception("Hotstring mouse observer failed")
        return user32.CallNextHookEx(self._mouse_handle, code, message, data)

    def _monitor_hook(self) -> None:
        """Renew the hook after window changes or when it has aged."""
        foreground = self._get_foreground_window()
        foreground_changed = foreground != self._observed_foreground_window
        self._observed_foreground_window = foreground
        if (
            foreground_changed
            and self._pending_checkpoint is not None
            and foreground != self._pending_checkpoint.context[0]
        ):
            identity = windows.get_window_identity(foreground)
            if identity is None or identity.process_id != os.getpid():
                self._cancel_pending(input_changed=True)
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
        if self._mouse_handle is not None:
            try:
                replacement_mouse = self._install_mouse_hook()
            except OSError:
                self._cancel_pending(input_changed=True)
                logger.exception("Could not refresh hotstring mouse observer")
            else:
                previous_mouse = self._mouse_handle
                self._mouse_handle = replacement_mouse
                if not user32.UnhookWindowsHookEx(previous_mouse):
                    logger.warning("Could not remove replaced hotstring mouse observer")
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
            self._cancel_pending(input_changed=True)
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
        owned_input = (
            event.flags & LLKHF_INJECTED
            and event.dwExtraInfo == keyboard_input.INPUT_MARKER
        )
        key_down = message in (WM_KEYDOWN, WM_SYSKEYDOWN)
        injected_modifier = (
            event.flags & LLKHF_INJECTED and event.vkCode in MODIFIER_KEYS
        )
        if (
            key_down
            and not owned_input
            and not injected_modifier
            and self._should_monitor()
        ):
            self._cancel_pending(input_changed=True)
        if event.flags & LLKHF_INJECTED:
            # Keep the original observational behavior: input helpers can
            # replay physical keys. Feeding or clearing those duplicates would
            # corrupt the trigger assembled from the physical events.
            return user32.CallNextHookEx(self._handle, code, message, data)
        if event.vkCode in MODIFIER_KEYS:
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
        if (
            self._pending_checkpoint is not None
            and self._pending_checkpoint.interactive.is_set()
        ):
            # A modal prompt pumps events. Do not recognize another hotstring
            # or replace the pending checkpoint while collecting its values.
            self._matcher.reset()
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
        if event.vkCode == VK_BACK and not altgr_down:
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
        if not character or (
            altgr_down and (not character.isprintable() or character.isspace())
        ):
            self._matcher.reset()
            return user32.CallNextHookEx(
                self._handle, HC_ACTION, message, data
            )
        snippet = self._matcher.character(character)
        if snippet is not None:
            checkpoint = InputCheckpoint(input_context)
            self._pending_checkpoint = checkpoint
            # Replaying punctuation by virtual key would translate it again
            # using modifiers that may have changed during a variable prompt.
            boundary = (
                event.vkCode
                if event.vkCode in (VK_SPACE, VK_RETURN, VK_TAB)
                else character
            )
            if self._on_match(snippet, boundary, checkpoint):
                return 1
        return user32.CallNextHookEx(self._handle, HC_ACTION, message, data)

    @staticmethod
    def _is_key_down(virtual_keys: frozenset[int]) -> bool:
        """Return whether any key in one modifier family is physically down."""
        return any(user32.GetAsyncKeyState(key) & 0x8000 for key in virtual_keys)

    @classmethod
    def _is_altgr_down(cls, event_flags: int) -> bool:
        """Recognize AltGr and its Ctrl+Alt equivalent for layout translation."""
        return bool(
            cls._is_key_down(CONTROL_KEYS)
            and (
                event_flags & LLKHF_ALTDOWN
                or cls._is_key_down(ALT_KEYS)
            )
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
    def _get_input_context(
        window: int | None = None,
    ) -> tuple[int | None, int | None, int | None]:
        """Identify foreground, focused child, and active keyboard layout."""
        foreground = window if window is not None else user32.GetForegroundWindow()
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
        # Observation must not change Windows' pending dead-key state before
        # the target application's TranslateMessage processes the same key.
        # Bit 2 preserves that state on Windows 10 1607 and newer.
        count = user32.ToUnicodeEx(
            virtual_key,
            scan_code,
            state,
            buffer,
            len(buffer),
            TO_UNICODE_NO_STATE_CHANGE,
            layout,
        )
        return buffer.value[:count] if count == 1 else None
