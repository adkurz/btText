"""Native appearance selection for btText's wx user interface."""

from __future__ import annotations

import wx

from core.app_settings import (
    APPEARANCE_DARK,
    APPEARANCE_LIGHT,
    APPEARANCE_SYSTEM,
)

def apply_to_app(app: wx.App, appearance: str = APPEARANCE_SYSTEM) -> None:
    """Request the configured native appearance before creating any windows."""
    native_appearances = {
        APPEARANCE_SYSTEM: wx.PyApp.Appearance.System,
        APPEARANCE_LIGHT: wx.PyApp.Appearance.Light,
        APPEARANCE_DARK: wx.PyApp.Appearance.Dark,
    }
    app.SetAppearance(native_appearances[appearance])
