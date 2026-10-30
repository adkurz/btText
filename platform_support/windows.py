"""Inspect and activate native Windows application windows."""

import ctypes
from collections.abc import Callable
import logging
import ntpath
import os
from ctypes import wintypes
from dataclasses import dataclass

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
UPDATE_SHUTDOWN_EVENT_NAME = r"Local\btText.UpdateShutdown"
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_SKIPOWNPROCESS = 0x0002
GA_ROOTOWNER = 3
_SHELL_WINDOW_CLASSES = frozenset((
    "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow",
    "TopLevelWindowForOverflowXamlIsland", "Progman", "WorkerW",
    "Xaml_WindowedPopupClass", "ThumbnailDeviceHelperWnd",
))

logger = logging.getLogger("bttext.windows")


@dataclass(frozen=True)
class WindowIdentity:
    """Stable ownership information captured for a native window handle."""

    handle: int
    thread_id: int
    process_id: int


user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
)
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.AttachThreadInput.argtypes = (
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.BOOL,
)
user32.AttachThreadInput.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
user32.SetFocus.argtypes = (wintypes.HWND,)
user32.SetFocus.restype = wintypes.HWND
user32.GetFocus.restype = wintypes.HWND
user32.IsChild.argtypes = (wintypes.HWND, wintypes.HWND)
user32.IsChild.restype = wintypes.BOOL
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
WINEVENTPROC = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
)
user32.SetWinEventHook.argtypes = (
    wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, WINEVENTPROC,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
)
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.UnhookWinEvent.argtypes = (wintypes.HANDLE,)
user32.UnhookWinEvent.restype = wintypes.BOOL
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = (
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CreateEventW.argtypes = (
    wintypes.LPVOID,
    wintypes.BOOL,
    wintypes.BOOL,
    wintypes.LPCWSTR,
)
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
kernel32.WaitForSingleObject.restype = wintypes.DWORD


class ForegroundWindowObserver:
    """Observe foreground changes on the registering thread's message loop."""

    def __init__(self, on_foreground: Callable[[int], None]) -> None:
        self._on_foreground = on_foreground
        self._handle = None
        self._callback = WINEVENTPROC(self._on_event)
        # Out-of-context delivery (the default) stays on the wx UI thread and
        # works independently of whether hotstring monitoring is enabled.
        self._handle = user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
            None, self._callback, 0, 0, WINEVENT_SKIPOWNPROCESS,
        )
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def _on_event(self, hook, event, window, object_id, child_id, thread, time):
        """Contain callback failures so they cannot unwind through Windows."""
        if not self._handle or event != EVENT_SYSTEM_FOREGROUND or not window:
            return
        try:
            # Use the event's HWND, even when the taskbar has since taken the
            # foreground. Reading GetForegroundWindow here would lose the app.
            self._on_foreground(int(window))
        except Exception:
            logger.exception("Could not remember the foreground window")

    def close(self) -> None:
        """Remove the observer on its registering thread; safe to call twice."""
        if self._handle:
            if not user32.UnhookWinEvent(self._handle):
                logger.warning("Could not remove the foreground window observer")
                return
            self._handle = None


class UpdateShutdownSignal:
    """Expose an auto-reset event through which the installer requests exit."""

    def __init__(self) -> None:
        """Create the process-owned side of the per-session update signal."""
        self._handle = kernel32.CreateEventW(
            None,
            False,
            False,
            UPDATE_SHUTDOWN_EVENT_NAME,
        )
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def consume(self) -> bool:
        """Return and reset a pending installer shutdown request."""
        if not self._handle:
            return False
        result = kernel32.WaitForSingleObject(self._handle, 0)
        if result == WAIT_OBJECT_0:
            return True
        if result == WAIT_TIMEOUT:
            return False
        raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        """Release the process-owned event handle; repeated calls are safe."""
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None


def get_foreground_window() -> int | None:
    """Return the current foreground window handle, if one exists."""
    handle = user32.GetForegroundWindow()
    return int(handle) if handle else None


def is_valid_window(handle: int | None) -> bool:
    """Return whether ``handle`` identifies an existing native window."""
    return bool(handle and user32.IsWindow(handle))


def get_window_identity(handle: int | None) -> WindowIdentity | None:
    """Capture ownership so a subsequently reused HWND can be rejected."""
    if not is_valid_window(handle):
        return None
    process_id = wintypes.DWORD()
    thread_id = user32.GetWindowThreadProcessId(
        handle,
        ctypes.byref(process_id),
    )
    if not thread_id or not process_id.value:
        return None
    return WindowIdentity(int(handle), int(thread_id), int(process_id.value))


def matches_window_identity(identity: WindowIdentity) -> bool:
    """Return whether an HWND still belongs to its captured owner."""
    return get_window_identity(identity.handle) == identity


def activate_window_identity(
    identity: WindowIdentity,
    *,
    focus_window: int | None = None,
) -> bool:
    """Activate the captured window, requiring any known input field to survive."""
    if not matches_window_identity(identity) or not activate_window(identity.handle):
        return False
    if not focus_window:
        # Some applications never expose a focused HWND. Keep their ordinary
        # window-activation path without confusing absent evidence with a lost
        # input field that was known when the hotstring was typed.
        return True
    if focus_window != identity.handle and not user32.IsChild(
        identity.handle, focus_window,
    ):
        return False
    target_thread = user32.GetWindowThreadProcessId(focus_window, None)
    current_thread = kernel32.GetCurrentThreadId()
    attach = target_thread != current_thread
    if not target_thread or (
        attach and not user32.AttachThreadInput(current_thread, target_thread, True)
    ):
        return False
    try:
        # Activation can pump the other application's events. Recheck ownership
        # and parentage before touching a child that may have been destroyed.
        if (
            not matches_window_identity(identity)
            or (
                focus_window != identity.handle
                and not user32.IsChild(identity.handle, focus_window)
            )
        ):
            return False
        user32.SetFocus(focus_window)
        return (
            user32.GetFocus() == focus_window
            and get_foreground_window() == identity.handle
        )
    finally:
        if attach:
            user32.AttachThreadInput(current_thread, target_thread, False)


def is_external_window(handle: int | None) -> bool:
    """Return whether handle belongs to another process and is still valid."""
    if not is_valid_window(handle):
        return False
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    return process_id.value != os.getpid()


def is_shell_window(handle: int) -> bool:
    """Exclude the shell and its owned popup windows from paste targets."""
    root_owner = user32.GetAncestor(handle, GA_ROOTOWNER)
    handles = (handle, root_owner) if root_owner and root_owner != handle else (handle,)
    class_name = ctypes.create_unicode_buffer(256)
    for candidate in handles:
        if not user32.GetClassNameW(candidate, class_name, len(class_name)):
            # A destroyed or unidentifiable window cannot establish a target.
            return True
        if class_name.value in _SHELL_WINDOW_CLASSES:
            return True
    # Win+B and the hidden-icons menu can report a separate popup rather than
    # the taskbar itself. Checking the owner also covers unnamed/new shell
    # popup classes without excluding ordinary application-owned dialogs.
    return False


def get_window_application_name(handle: int | None) -> str | None:
    """Return a window's executable filename without exposing its full path."""
    if not is_valid_window(handle):
        return None
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    if not process_id.value:
        return None
    process = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        process_id.value,
    )
    if not process:
        return None
    try:
        capacity = wintypes.DWORD(32768)
        path_buffer = ctypes.create_unicode_buffer(capacity.value)
        if not kernel32.QueryFullProcessImageNameW(
            process,
            0,
            path_buffer,
            ctypes.byref(capacity),
        ):
            return None
        return ntpath.basename(path_buffer.value) or None
    finally:
        kernel32.CloseHandle(process)


def activate_window(handle: int | None) -> bool:
    """Activate a valid window, restoring it only if it is minimized."""
    if not is_valid_window(handle):
        return False
    # Restoring a maximized or snapped window resets its size and position.
    if user32.IsIconic(handle):
        user32.ShowWindow(handle, SW_RESTORE)
    user32.SetForegroundWindow(handle)
    if get_foreground_window() == handle:
        return True

    foreground_window = get_foreground_window()
    if not foreground_window:
        return False
    foreground_thread = user32.GetWindowThreadProcessId(
        foreground_window,
        None,
    )
    current_thread = kernel32.GetCurrentThreadId()
    if not foreground_thread or foreground_thread == current_thread:
        return False
    if not user32.AttachThreadInput(current_thread, foreground_thread, True):
        return False
    try:
        user32.BringWindowToTop(handle)
        user32.SetForegroundWindow(handle)
        user32.SetFocus(handle)
    finally:
        user32.AttachThreadInput(current_thread, foreground_thread, False)
    return get_foreground_window() == handle
