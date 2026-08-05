"""Shared wx controls with application-specific accessibility behavior."""

import wx


class FocusableReadOnlyTextCtrl(wx.TextCtrl):
    """Read-only text that remains reachable during keyboard navigation."""

    def __init__(self, parent, value: str = "", style: int = 0):
        """Create a read-only control that still participates in tab order."""
        super().__init__(parent, value=value, style=style | wx.TE_READONLY)

    def AcceptsFocusFromKeyboard(self) -> bool:
        """Keep the read-only field reachable to keyboard users."""
        return self.IsEnabled() and self.IsShown()
