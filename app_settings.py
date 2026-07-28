"""Application settings and portable representations of global hotkeys."""

import dataclasses
import re
import sys
from ctypes import create_unicode_buffer, windll
from configparser import ConfigParser, Error as ConfigParserError
from pathlib import Path

import i18n
from user_errors import UserFacingError


class SettingsError(UserFacingError):
    """Raised when application settings cannot be loaded or saved."""


class HotkeyError(UserFacingError, ValueError):
    """Raised when a hotkey representation is invalid."""


SPECIAL_KEY_CODES = {
    "BACKSPACE": 0x08,
    "ENTER": 0x0D,
    "PAUSE": 0x13,
    "CAPSLOCK": 0x14,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "PRINTSCREEN": 0x2C,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "NUMLOCK": 0x90,
    "SCROLLLOCK": 0x91,
}
KEY_CODE_NAMES = {value: key for key, value in SPECIAL_KEY_CODES.items()}
MODIFIER_KEY_CODES = {
    0x10,  # Shift
    0x11,  # Control
    0x12,  # Alt
    0x5B,  # Left Windows
    0x5C,  # Right Windows
    0xA0,  # Left Shift
    0xA1,  # Right Shift
    0xA2,  # Left Control
    0xA3,  # Right Control
    0xA4,  # Left Alt
    0xA5,  # Right Alt / AltGr
}


@dataclasses.dataclass(frozen=True)
class Hotkey:
    """A validated global hotkey independent of wxPython key constants."""
    key: str
    control: bool = False
    shift: bool = False
    alt: bool = False
    windows: bool = False

    def __post_init__(self):
        """Normalize the key and reject unsupported modifier combinations."""
        normalized_key = self.key.upper()
        if not self._is_supported_key(normalized_key):
            raise HotkeyError(
                "hotkey_key_unsupported",
                "The hotkey contains an unsupported key",
            )
        if not (self.control or self.shift or self.alt or self.windows):
            raise HotkeyError(
                "hotkey_modifier_required",
                "The hotkey requires at least one modifier",
            )
        object.__setattr__(self, "key", normalized_key)

    @staticmethod
    def _is_supported_key(key: str) -> bool:
        """Return whether a serialized key name maps to a usable virtual key."""
        if key in SPECIAL_KEY_CODES:
            return True
        if re.fullmatch(r"VK_[0-9A-F]{2}", key):
            key_code = int(key[3:], 16)
            return key_code not in MODIFIER_KEY_CODES and key_code != 0
        if len(key) == 1 and ("A" <= key <= "Z" or "0" <= key <= "9"):
            return True
        if key.startswith("F") and key[1:].isdigit():
            return 1 <= int(key[1:]) <= 24
        return False

    @classmethod
    def parse(cls, value: str):
        """Parse the stable, locale-independent representation used on disk."""
        parts = [part.strip() for part in value.split("+")]
        if not parts or any(not part for part in parts):
            raise HotkeyError(
                "hotkey_format_invalid",
                "The hotkey has an invalid format",
            )

        modifiers = {
            "CTRL": False,
            "SHIFT": False,
            "ALT": False,
            "WIN": False,
        }
        keys = []
        for part in parts:
            normalized_part = part.upper()
            if normalized_part in modifiers:
                if modifiers[normalized_part]:
                    raise HotkeyError(
                        "hotkey_modifier_duplicate",
                        "The hotkey contains a duplicate modifier",
                    )
                modifiers[normalized_part] = True
            else:
                keys.append(part)
        if len(keys) != 1:
            raise HotkeyError(
                "hotkey_key_count_invalid",
                "The hotkey must contain exactly one key",
            )

        return cls(
            key=keys[0],
            control=modifiers["CTRL"],
            shift=modifiers["SHIFT"],
            alt=modifiers["ALT"],
            windows=modifiers["WIN"],
        )

    @classmethod
    def key_from_code(cls, key_code: int) -> str:
        """Convert a usable Windows virtual-key code to stored form."""
        if key_code in MODIFIER_KEY_CODES or not 1 <= key_code <= 0xFE:
            raise HotkeyError(
                "hotkey_key_unusable",
                "The key cannot be used as a hotkey",
            )
        if ord("A") <= key_code <= ord("Z"):
            return chr(key_code)
        if ord("0") <= key_code <= ord("9"):
            return chr(key_code)
        if 0x70 <= key_code <= 0x87:
            return "F{}".format(key_code - 0x6F)
        if key_code in KEY_CODE_NAMES:
            return KEY_CODE_NAMES[key_code]
        return "VK_{:02X}".format(key_code)

    @property
    def key_code(self) -> int:
        """Return the Windows virtual-key code for this hotkey."""
        if len(self.key) == 1:
            return ord(self.key)
        if self.key.startswith("F"):
            return 0x6F + int(self.key[1:])
        if self.key in SPECIAL_KEY_CODES:
            return SPECIAL_KEY_CODES[self.key]
        return int(self.key[3:], 16)

    def get_key_label(self) -> str:
        """Return the localized Windows label used only for presentation."""
        if not self.key.startswith("VK_"):
            return self.key
        if sys.platform == "win32":
            scan_code = windll.user32.MapVirtualKeyW(
                self.key_code,
                4,  # MAPVK_VK_TO_VSC_EX
            )
            key_data = (scan_code & 0xFF) << 16
            if scan_code & 0xFF00 in (0xE000, 0xE100):
                key_data |= 1 << 24
            buffer = create_unicode_buffer(64)
            if windll.user32.GetKeyNameTextW(key_data, buffer, 64):
                return buffer.value
        return self.key

    def to_display_string(self) -> str:
        """Return a localized label suitable for the settings UI."""
        parts = []
        if self.control:
            # Translators: Abbreviated Control-key name in a displayed shortcut,
            # for example "Ctrl+Alt+T".
            parts.append(i18n.pgettext("hotkey modifier", "Ctrl"))
        if self.shift:
            # Translators: Shift-key name in a displayed keyboard shortcut.
            parts.append(i18n.pgettext("hotkey modifier", "Shift"))
        if self.alt:
            # Translators: Alt-key name in a displayed keyboard shortcut.
            parts.append(i18n.pgettext("hotkey modifier", "Alt"))
        if self.windows:
            # Translators: Abbreviated Windows-key name in a displayed shortcut.
            parts.append(i18n.pgettext("hotkey modifier", "Win"))
        parts.append(self.get_key_label())
        return "+".join(parts)

    def __str__(self) -> str:
        """Return the stable representation written to the settings file."""
        parts = []
        if self.control:
            parts.append("CTRL")
        if self.shift:
            parts.append("SHIFT")
        if self.alt:
            parts.append("ALT")
        if self.windows:
            parts.append("WIN")
        parts.append(self.key)
        return "+".join(parts)


DEFAULT_TOGGLE_HOTKEY = Hotkey(
    key="T",
    control=True,
    shift=True,
    alt=True,
)


@dataclasses.dataclass(frozen=True)
class AppSettings:
    """Immutable collection of user-configurable application settings."""
    toggle_window_hotkey: Hotkey = DEFAULT_TOGGLE_HOTKEY
    language: str = i18n.SYSTEM_LANGUAGE
    include_copied_text_in_clipboard_history: bool = True
    allow_copied_text_cloud_upload: bool = True
    hotstrings_enabled: bool = True
    preserve_hotstring_boundary: bool = True
    notify_hotstring_expansion: bool = False


class SettingsStore:
    """Load and atomically replace the application's INI settings file."""
    def __init__(
        self,
        settings_file: str | Path,
        locale_directory: str | Path | None = None,
    ):
        """Store settings and optionally validate languages against catalogs."""
        self.settings_file = Path(settings_file)
        self.locale_directory = (
            Path(locale_directory)
            if locale_directory is not None
            else None
        )

    def load(self) -> AppSettings:
        """Load settings, using defaults when the file or key is absent."""
        parser = ConfigParser()
        try:
            parser.read(self.settings_file, encoding="utf-8")
            value = parser.get(
                "hotkeys",
                "toggle_window",
                fallback=str(DEFAULT_TOGGLE_HOTKEY),
            )
            language = i18n.validate_language(
                parser.get(
                    "general",
                    "language",
                    fallback=i18n.SYSTEM_LANGUAGE,
                ),
                self.locale_directory,
            )
            include_copied_text_in_clipboard_history = parser.getboolean(
                "general",
                "include_copied_text_in_clipboard_history",
                fallback=True,
            )
            allow_copied_text_cloud_upload = parser.getboolean(
                "general",
                "allow_copied_text_cloud_upload",
                fallback=True,
            )
            hotstrings_enabled = parser.getboolean(
                "hotstrings", "enabled", fallback=True
            )
            preserve_hotstring_boundary = parser.getboolean(
                "hotstrings", "preserve_boundary", fallback=True
            )
            notify_hotstring_expansion = parser.getboolean(
                "hotstrings", "notify_expansion", fallback=False
            )
            return AppSettings(
                toggle_window_hotkey=Hotkey.parse(value),
                language=language,
                include_copied_text_in_clipboard_history=(
                    include_copied_text_in_clipboard_history
                ),
                allow_copied_text_cloud_upload=allow_copied_text_cloud_upload,
                hotstrings_enabled=hotstrings_enabled,
                preserve_hotstring_boundary=preserve_hotstring_boundary,
                notify_hotstring_expansion=notify_hotstring_expansion,
            )
        except (ConfigParserError, OSError, ValueError) as error:
            raise SettingsError(
                "settings_read_failed",
                "The settings file could not be read: {reason}",
                reason=error,
            ) from error

    def save(self, settings: AppSettings) -> None:
        """Atomically save a complete settings file."""
        # Replace a complete temporary file so an interrupted write cannot
        # leave a truncated settings file behind.
        temporary_file = self.settings_file.with_suffix(
            self.settings_file.suffix + ".tmp"
        )
        try:
            parser = ConfigParser()
            parser["general"] = {
                "language": i18n.validate_language(
                    settings.language,
                    self.locale_directory,
                ),
                "include_copied_text_in_clipboard_history": str(
                    settings.include_copied_text_in_clipboard_history
                ),
                "allow_copied_text_cloud_upload": str(
                    settings.allow_copied_text_cloud_upload
                ),
            }
            parser["hotstrings"] = {
                "enabled": str(settings.hotstrings_enabled),
                "preserve_boundary": str(
                    settings.preserve_hotstring_boundary
                ),
                "notify_expansion": str(settings.notify_hotstring_expansion),
            }
            parser["hotkeys"] = {
                "toggle_window": str(settings.toggle_window_hotkey),
            }
            with temporary_file.open("w", encoding="utf-8") as file:
                parser.write(file)
            temporary_file.replace(self.settings_file)
        except (OSError, ValueError) as error:
            try:
                temporary_file.unlink(missing_ok=True)
            except OSError:
                pass
            raise SettingsError(
                "settings_save_failed",
                "The settings file could not be saved: {reason}",
                reason=error,
            ) from error
