"""System-driven colours for btText's wx user interface."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys

import wx

from core.app_settings import (
    APPEARANCE_DARK,
    APPEARANCE_LIGHT,
    APPEARANCE_SYSTEM,
)


DWMWA_USE_IMMERSIVE_DARK_MODE = 20


@dataclass(frozen=True)
class Theme:
    """Colours used for an application appearance."""

    dark: bool
    window_background: wx.Colour
    control_background: wx.Colour
    foreground: wx.Colour


_LIGHT_THEME = Theme(
    dark=False,
    window_background=wx.Colour(240, 240, 240),
    control_background=wx.Colour(255, 255, 255),
    foreground=wx.Colour(0, 0, 0),
)
_DARK_THEME = Theme(
    dark=True,
    window_background=wx.Colour(32, 32, 32),
    control_background=wx.Colour(24, 24, 24),
    foreground=wx.Colour(240, 240, 240),
)
_active_theme: Theme | None = None


def system_uses_dark_mode() -> bool:
    """Return whether the system uses a dark appearance."""
    if sys.platform == "win32":
        windows_dark_mode = _windows_uses_dark_mode()
        if windows_dark_mode is not None:
            return windows_dark_mode

    get_appearance = getattr(wx.SystemSettings, "GetAppearance", None)
    if get_appearance is None:
        return False
    return bool(get_appearance().IsDark())


def _windows_uses_dark_mode() -> bool | None:
    """Read the Windows app appearance preference, if it is available."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _value_type = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except (ImportError, OSError, TypeError, ValueError):
        return None
    return not bool(value)


def initialize(appearance: str = APPEARANCE_SYSTEM) -> Theme:
    """Select and retain the configured appearance for this application run."""
    global _active_theme
    use_dark_theme = (
        appearance == APPEARANCE_DARK
        or (
            appearance == APPEARANCE_SYSTEM
            and system_uses_dark_mode()
        )
    )
    if use_dark_theme:
        _active_theme = _DARK_THEME
    else:
        _active_theme = _LIGHT_THEME
    return _active_theme


def get_active_theme() -> Theme:
    """Return the startup theme, initializing it on first use if necessary."""
    return _active_theme if _active_theme is not None else initialize()


def apply_to_app(app: wx.App) -> None:
    """Request the selected native appearance before creating any windows."""
    active_theme = get_active_theme()
    appearance = (
        wx.PyApp.Appearance.Dark
        if active_theme.dark
        else wx.PyApp.Appearance.Light
    )
    app.SetAppearance(appearance)


def apply(window: wx.Window) -> None:
    """Apply the startup theme to a window and all existing descendants."""
    active_theme = get_active_theme()
    _apply_to_window(window, active_theme)
    for child in window.GetChildren():
        _apply_tree(child, active_theme)
    if isinstance(window, wx.TopLevelWindow):
        _apply_windows_title_bar(window, active_theme.dark)


def _apply_tree(window: wx.Window, active_theme: Theme) -> None:
    """Apply one theme recursively without resolving it again."""
    _apply_to_window(window, active_theme)
    for child in window.GetChildren():
        _apply_tree(child, active_theme)


def _apply_to_window(window: wx.Window, active_theme: Theme) -> None:
    """Set colours appropriate for one wx control."""
    is_text_surface = isinstance(window, (wx.TextCtrl, wx.TreeCtrl, wx.ListCtrl))
    background = (
        active_theme.control_background
        if is_text_surface
        else active_theme.window_background
    )
    window.SetBackgroundColour(background)
    window.SetForegroundColour(active_theme.foreground)
    window.Refresh()


def _apply_windows_title_bar(window: wx.TopLevelWindow, dark: bool) -> None:
    """Ask Windows to match a top-level title bar to the active appearance."""
    if sys.platform != "win32":
        return
    try:
        attribute_value = wintypes.BOOL(dark)
        handle = ctypes.c_void_p(window.GetHandle())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            handle,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(attribute_value),
            ctypes.sizeof(attribute_value),
        )
    except (AttributeError, OSError, TypeError, ValueError):
        # Colouring the client area is still useful on unsupported systems.
        return
