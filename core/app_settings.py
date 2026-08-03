"""Application settings and mode-aware INI-file persistence."""

import dataclasses
from configparser import ConfigParser, Error as ConfigParserError
from pathlib import Path

import i18n
from core.shortcuts import DEFAULT_TOGGLE_HOTKEY, Hotkey
from core.user_errors import UserFacingError

APPEARANCE_SYSTEM = "system"
APPEARANCE_LIGHT = "light"
APPEARANCE_DARK = "dark"
APPEARANCES = (APPEARANCE_SYSTEM, APPEARANCE_LIGHT, APPEARANCE_DARK)


class SettingsError(UserFacingError):
    """Raised when application settings cannot be loaded or saved."""


@dataclasses.dataclass(frozen=True)
class AppSettings:
    """Immutable collection of user-configurable application settings."""

    database_file: str | None = None
    toggle_window_hotkey: Hotkey = DEFAULT_TOGGLE_HOTKEY
    language: str = i18n.SYSTEM_LANGUAGE
    appearance: str = APPEARANCE_SYSTEM
    include_copied_text_in_clipboard_history: bool = True
    allow_copied_text_cloud_upload: bool = True
    hotstrings_enabled: bool = True
    preserve_hotstring_boundary: bool = True
    notify_hotstring_expansion: bool = False

    def __post_init__(self):
        """Normalize a configured database path once at the settings boundary."""
        if self.database_file is not None:
            object.__setattr__(
                self,
                "database_file",
                str(Path(self.database_file).expanduser().resolve()),
            )


class SettingsStore:
    """Load and atomically replace settings in the active data directory."""

    def __init__(
        self,
        settings_file: str | Path,
        locale_directory: str | Path | None = None,
    ):
        """Store settings and optionally validate languages against catalogs."""
        self.settings_file = Path(settings_file)
        self.locale_directory = (
            Path(locale_directory) if locale_directory is not None else None
        )

    def load(self) -> AppSettings:
        """Load settings, using defaults when the file or key is absent."""
        defaults = AppSettings()
        parser = ConfigParser()
        try:
            parser.read(self.settings_file, encoding="utf-8")
            value = parser.get(
                "hotkeys",
                "toggle_window",
                fallback=str(defaults.toggle_window_hotkey),
            )
            language = i18n.validate_language(
                parser.get(
                    "general",
                    "language",
                    fallback=defaults.language,
                ),
                self.locale_directory,
            )
            appearance = parser.get(
                "design",
                "appearance",
                fallback=defaults.appearance,
            ).casefold()
            if appearance not in APPEARANCES:
                appearance = defaults.appearance
            database_file = parser.get(
                "general",
                "database_file",
                fallback=defaults.database_file,
            )
            if database_file is not None:
                database_path = Path(database_file).expanduser()
                if not database_path.is_absolute():
                    database_path = self.settings_file.parent / database_path
                database_file = str(database_path.resolve())
            include_copied_text_in_clipboard_history = parser.getboolean(
                "general",
                "include_copied_text_in_clipboard_history",
                fallback=defaults.include_copied_text_in_clipboard_history,
            )
            allow_copied_text_cloud_upload = parser.getboolean(
                "general",
                "allow_copied_text_cloud_upload",
                fallback=defaults.allow_copied_text_cloud_upload,
            )
            hotstrings_enabled = parser.getboolean(
                "hotstrings",
                "enabled",
                fallback=defaults.hotstrings_enabled,
            )
            preserve_hotstring_boundary = parser.getboolean(
                "hotstrings",
                "preserve_boundary",
                fallback=defaults.preserve_hotstring_boundary,
            )
            notify_hotstring_expansion = parser.getboolean(
                "hotstrings",
                "notify_expansion",
                fallback=defaults.notify_hotstring_expansion,
            )
            return AppSettings(
                database_file=database_file,
                toggle_window_hotkey=Hotkey.parse(value),
                language=language,
                appearance=appearance,
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
            parser["design"] = {
                "appearance": (
                    settings.appearance
                    if settings.appearance in APPEARANCES
                    else APPEARANCE_SYSTEM
                ),
            }
            if settings.database_file is not None:
                database_path = Path(settings.database_file).expanduser().resolve()
                settings_directory = self.settings_file.parent.resolve()
                # Keep the database path portable within whichever data
                # directory is active. Databases elsewhere remain explicit
                # absolute paths.
                parser["general"]["database_file"] = (
                    database_path.name
                    if database_path.parent == settings_directory
                    else str(database_path)
                )
            parser["hotstrings"] = {
                "enabled": str(settings.hotstrings_enabled),
                "preserve_boundary": str(settings.preserve_hotstring_boundary),
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
