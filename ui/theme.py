"""System-driven colours for btText's wx user interface."""

from __future__ import annotations

from dataclasses import dataclass

import wx

from core.app_settings import (
    APPEARANCE_DARK,
    APPEARANCE_LIGHT,
    APPEARANCE_SYSTEM,
)

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


def get_active_theme() -> Theme:
    """Return the appearance selected by wx for this application run."""
    if _active_theme is not None:
        return _active_theme
    return _theme_for_current_appearance()


def apply_to_app(app: wx.App, appearance: str = APPEARANCE_SYSTEM) -> None:
    """Request the configured native appearance before creating any windows."""
    native_appearances = {
        APPEARANCE_SYSTEM: wx.PyApp.Appearance.System,
        APPEARANCE_LIGHT: wx.PyApp.Appearance.Light,
        APPEARANCE_DARK: wx.PyApp.Appearance.Dark,
    }
    app.SetAppearance(native_appearances[appearance])

    global _active_theme
    _active_theme = _theme_for_current_appearance()


def _theme_for_current_appearance() -> Theme:
    """Return custom colours matching the current wx application appearance."""
    if wx.SystemSettings.GetAppearance().IsDark():
        return _DARK_THEME
    return _LIGHT_THEME


def apply(window: wx.Window) -> None:
    """Apply the startup theme to a window and all existing descendants."""
    active_theme = get_active_theme()
    _apply_to_window(window, active_theme)
    for child in window.GetChildren():
        _apply_tree(child, active_theme)


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
