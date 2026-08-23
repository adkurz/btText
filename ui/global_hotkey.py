"""wxPython lifecycle management for one global keyboard shortcut."""

import wx

from core.shortcuts import Hotkey
from platform_support.shortcuts import (
    activate_keyboard_layout,
    get_foreground_keyboard_layout,
)


class WxGlobalHotkeyBinding:
    """Register and temporarily suspend one wx global hotkey binding."""

    def __init__(self, window: wx.Window, hotkey_id: int):
        """Initialize an unregistered binding for ``window``."""
        self._window = window
        self.hotkey_id = hotkey_id
        self.registered_hotkey: Hotkey | None = None
        self._suspended = False
        self._restore_on_resume = False
        self._keyboard_layout = get_foreground_keyboard_layout()

    def register(self, hotkey: Hotkey) -> bool:
        """Register ``hotkey`` and remember it only after success."""
        success = self._window.RegisterHotKey(
            self.hotkey_id,
            self._get_modifiers(hotkey),
            hotkey.key_code,
        )
        if success:
            self.registered_hotkey = hotkey
        return success

    def unregister(self) -> None:
        """Release the currently registered hotkey, if any."""
        if self.registered_hotkey is None:
            return
        self._window.UnregisterHotKey(self.hotkey_id)
        self.registered_hotkey = None

    def suspend(self) -> None:
        """Release the hotkey until a later call to ``resume``."""
        self._restore_on_resume = self.registered_hotkey is not None
        self._suspended = True
        self.unregister()

    def resume(self, hotkey: Hotkey) -> bool:
        """End suspension and restore ``hotkey`` when none is registered."""
        if not self._suspended:
            return True
        self._suspended = False
        if self.registered_hotkey is not None:
            self._restore_on_resume = False
            return True
        if not self._restore_on_resume:
            return True
        self._restore_on_resume = False
        return self.register(hotkey)

    def refresh_keyboard_layout(self) -> Hotkey | None:
        """Re-register after a layout change and return a failed hotkey."""
        keyboard_layout = get_foreground_keyboard_layout()
        if keyboard_layout is None or keyboard_layout == self._keyboard_layout:
            return None
        self._keyboard_layout = keyboard_layout
        activate_keyboard_layout(keyboard_layout)
        if self._suspended or self.registered_hotkey is None:
            return None
        hotkey = self.registered_hotkey
        self.unregister()
        return None if self.register(hotkey) else hotkey

    @staticmethod
    def _get_modifiers(hotkey: Hotkey) -> int:
        """Translate portable modifiers to wxPython registration flags."""
        modifiers = 0
        if hotkey.control:
            modifiers |= wx.MOD_CONTROL
        if hotkey.shift:
            modifiers |= wx.MOD_SHIFT
        if hotkey.alt:
            modifiers |= wx.MOD_ALT
        if hotkey.windows:
            modifiers |= wx.MOD_WIN
        return modifiers
