"""Localized presentation of keyboard shortcuts."""

import i18n
from core.shortcuts import Hotkey
from platform_support.shortcuts import get_key_label


def format_hotkey(hotkey: Hotkey) -> str:
    """Return a localized shortcut label suitable for the user interface."""
    parts = []
    if hotkey.control:
        # Translators: Abbreviated Control-key name in a displayed shortcut,
        # for example "Ctrl+Alt+T".
        parts.append(i18n.pgettext("hotkey modifier", "Ctrl"))
    if hotkey.shift:
        # Translators: Shift-key name in a displayed keyboard shortcut.
        parts.append(i18n.pgettext("hotkey modifier", "Shift"))
    if hotkey.alt:
        # Translators: Alt-key name in a displayed keyboard shortcut.
        parts.append(i18n.pgettext("hotkey modifier", "Alt"))
    if hotkey.windows:
        # Translators: Abbreviated Windows-key name in a displayed shortcut.
        parts.append(i18n.pgettext("hotkey modifier", "Win"))
    parts.append(get_key_label(hotkey))
    return "+".join(parts)
