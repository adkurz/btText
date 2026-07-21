import dataclasses
import re
import sys
from ctypes import create_unicode_buffer, windll
from configparser import ConfigParser, Error as ConfigParserError
from pathlib import Path


class SettingsError(Exception):
    pass


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
LITERAL_KEY_CODES = {
    ",": 0xBC,
    ".": 0xBE,
    "^": 0xC0,
    "ß": 0xBD,
    "´": 0xBB,
    "<": 0xE2,
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
    key: str
    control: bool = False
    shift: bool = False
    alt: bool = False
    windows: bool = False

    def __post_init__(self):
        if self.key in LITERAL_KEY_CODES:
            normalized_key = self.key
        else:
            normalized_key = self.key.upper()
        if not self._is_supported_key(normalized_key):
            raise ValueError("The hotkey contains an unsupported key")
        if not (self.control or self.shift or self.alt or self.windows):
            raise ValueError("The hotkey requires at least one modifier")
        object.__setattr__(self, "key", normalized_key)

    @staticmethod
    def _is_supported_key(key: str) -> bool:
        if key in LITERAL_KEY_CODES:
            return True
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
        parts = [part.strip() for part in value.split("+")]
        if not parts or any(not part for part in parts):
            raise ValueError("The hotkey has an invalid format")

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
                    raise ValueError("The hotkey contains a duplicate modifier")
                modifiers[normalized_part] = True
            else:
                keys.append(part)
        if len(keys) != 1:
            raise ValueError("The hotkey must contain exactly one key")

        return cls(
            key=keys[0],
            control=modifiers["CTRL"],
            shift=modifiers["SHIFT"],
            alt=modifiers["ALT"],
            windows=modifiers["WIN"],
        )

    @classmethod
    def key_from_code(cls, key_code: int) -> str:
        if key_code in MODIFIER_KEY_CODES or not 1 <= key_code <= 0xFE:
            raise ValueError("The key cannot be used as a hotkey")
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
        if self.key in LITERAL_KEY_CODES:
            return LITERAL_KEY_CODES[self.key]
        if len(self.key) == 1:
            return ord(self.key)
        if self.key.startswith("F"):
            return 0x6F + int(self.key[1:])
        if self.key in SPECIAL_KEY_CODES:
            return SPECIAL_KEY_CODES[self.key]
        return int(self.key[3:], 16)

    def get_key_label(self) -> str:
        if not self.key.startswith("VK_"):
            return self.key
        if sys.platform == "win32":
            scan_code = windll.user32.MapVirtualKeyW(self.key_code, 0)
            buffer = create_unicode_buffer(64)
            if windll.user32.GetKeyNameTextW(scan_code << 16, buffer, 64):
                return buffer.value
        return self.key

    def to_display_string(self) -> str:
        parts = []
        if self.control:
            parts.append("CTRL")
        if self.shift:
            parts.append("SHIFT")
        if self.alt:
            parts.append("ALT")
        if self.windows:
            parts.append("WIN")
        parts.append(self.get_key_label())
        return "+".join(parts)

    def __str__(self) -> str:
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
    toggle_window_hotkey: Hotkey = DEFAULT_TOGGLE_HOTKEY


class SettingsStore:
    def __init__(self, settings_file: str | Path):
        self.settings_file = Path(settings_file)

    def load(self) -> AppSettings:
        parser = ConfigParser()
        try:
            parser.read(self.settings_file, encoding="utf-8")
            value = parser.get(
                "hotkeys",
                "toggle_window",
                fallback=str(DEFAULT_TOGGLE_HOTKEY),
            )
            return AppSettings(toggle_window_hotkey=Hotkey.parse(value))
        except (ConfigParserError, OSError, ValueError) as error:
            raise SettingsError(
                "The settings file could not be read: {}".format(error)
            ) from error

    def save(self, settings: AppSettings) -> None:
        parser = ConfigParser()
        parser["hotkeys"] = {
            "toggle_window": str(settings.toggle_window_hotkey),
        }
        temporary_file = self.settings_file.with_suffix(
            self.settings_file.suffix + ".tmp"
        )
        try:
            with temporary_file.open("w", encoding="utf-8") as file:
                parser.write(file)
            temporary_file.replace(self.settings_file)
        except OSError as error:
            try:
                temporary_file.unlink(missing_ok=True)
            except OSError:
                pass
            raise SettingsError(
                "The settings file could not be saved: {}".format(error)
            ) from error
