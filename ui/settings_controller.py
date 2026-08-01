"""Apply and persist settings with runtime rollback on failure."""

import dataclasses

import wx

from core.app_settings import AppSettings, SettingsError, SettingsStore
from core.error_messages import format_user_error
from core.shortcuts import Hotkey
from i18n import _
from ui.global_hotkey import WxGlobalHotkeyBinding
from ui.hotstring_controller import HotstringController
from ui.shortcut_display import format_hotkey


class SettingsController:
    """Coordinate persisted settings with hotkey and hotstring state."""

    def __init__(
        self,
        parent: wx.Window,
        store: SettingsStore,
        settings: AppSettings,
        global_hotkey: WxGlobalHotkeyBinding,
        hotstrings: HotstringController,
    ):
        """Retain settings and the runtime integrations they control."""
        self._parent = parent
        self._store = store
        self._settings = settings
        self._global_hotkey = global_hotkey
        self._hotstrings = hotstrings
        self._hotstrings_running = False

    @property
    def settings(self) -> AppSettings:
        """Return the currently active settings."""
        return self._settings

    def register_initial_hotkey(self) -> bool:
        """Register the configured hotkey during application startup."""
        return self._register_hotkey(self._settings.toggle_window_hotkey)

    def start_initial_hotstrings(self) -> bool:
        """Load hotstrings and start monitoring when currently configured."""
        self._hotstrings.refresh()
        if not self._settings.hotstrings_enabled:
            return True
        self._hotstrings_running = self._hotstrings.start()
        return self._hotstrings_running

    def unregister_hotkey(self) -> None:
        """Release the currently registered global hotkey."""
        self._global_hotkey.unregister()

    def suspend_hotkey(self) -> None:
        """Temporarily release the hotkey while the dialog records."""
        self._global_hotkey.suspend()

    def resume_hotkey(self) -> None:
        """Re-register the configured hotkey after temporary suspension."""
        hotkey = self._settings.toggle_window_hotkey
        if not self._global_hotkey.resume(hotkey):
            self.show_hotkey_registration_error(hotkey)

    def show_hotkey_registration_error(self, hotkey: Hotkey) -> None:
        """Show the standard global hotkey registration error."""
        wx.MessageBox(
            # Translators: Startup error shown when btText cannot claim its
            # global shortcut. {} is a shortcut such as Ctrl+Alt+T.
            _(
                "The global hotkey {} is already in use and could not "
                "be registered."
            ).format(format_hotkey(hotkey)),
            # Translators: Title of an error registering a global shortcut.
            _("Hotkey error"),
            wx.OK | wx.ICON_ERROR,
            self._parent,
        )

    def apply(
        self,
        hotkey: Hotkey,
        language: str,
        appearance: str,
        include_copied_text_in_clipboard_history: bool,
        allow_copied_text_cloud_upload: bool,
        hotstrings_enabled: bool,
        preserve_hotstring_boundary: bool,
        notify_hotstring_expansion: bool,
    ) -> bool:
        """Apply and persist settings, rolling runtime state back on failure."""
        old_hotkey = self._settings.toggle_window_hotkey
        hotkey_changed = hotkey != old_hotkey
        hotstrings_started = False
        if hotstrings_enabled and not self._hotstrings_running:
            if not self._hotstrings.start():
                return False
            self._hotstrings_running = True
            hotstrings_started = True
        if hotkey_changed:
            self.unregister_hotkey()
        if hotkey_changed and not self._register_hotkey(
            hotkey,
            show_error=False,
        ):
            restored = self._register_hotkey(old_hotkey, show_error=False)
            if restored:
                # Translators: Settings error: the requested global shortcut is
                # occupied, so btText kept the old one. {} is such as Ctrl+Alt+T.
                message = _(
                    "The selected hotkey {} is already in use. "
                    "The previous hotkey has been restored."
                ).format(format_hotkey(hotkey))
            else:
                # Translators: Settings error: the requested shortcut is occupied
                # and restoring the old one also failed. {} is such as Ctrl+Alt+T.
                message = _(
                    "The selected hotkey {} is already in use and the previous "
                    "hotkey could not be restored. No global hotkey is active."
                ).format(format_hotkey(hotkey))
            wx.MessageBox(
                message,
                # Translators: Title of an error changing the global shortcut.
                _("Hotkey error"),
                wx.OK | wx.ICON_ERROR,
                self._parent,
            )
            if hotstrings_started:
                self._hotstrings.stop()
                self._hotstrings_running = False
            return False

        new_settings = AppSettings(
            database_file=self._settings.database_file,
            toggle_window_hotkey=hotkey,
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
        try:
            self._store.save(new_settings)
        except SettingsError as error:
            if hotstrings_started:
                self._hotstrings.stop()
                self._hotstrings_running = False
            if hotkey_changed:
                self.unregister_hotkey()
            restored = (
                not hotkey_changed
                or self._register_hotkey(old_hotkey, show_error=False)
            )
            if hotkey_changed and not restored:
                wx.MessageBox(
                    # Translators: Error after cancelling settings when btText
                    # could not restore the previously active global shortcut.
                    _(
                        "The previous hotkey could not be restored. No global "
                        "hotkey is active."
                    ),
                    # Translators: Title of an error restoring a global shortcut.
                    _("Hotkey error"),
                    wx.OK | wx.ICON_ERROR,
                    self._parent,
                )
            self._show_settings_error(error)
            return False
        self._settings = new_settings
        if not hotstrings_enabled:
            self._hotstrings.stop()
            self._hotstrings_running = False
        return True

    def save_database_file(self, database_file: str) -> bool:
        """Persist a database path while retaining every other setting."""
        new_settings = dataclasses.replace(
            self._settings,
            database_file=database_file,
        )
        try:
            self._store.save(new_settings)
        except SettingsError as error:
            self._show_settings_error(error)
            return False
        self._settings = new_settings
        return True

    def _register_hotkey(
        self,
        hotkey: Hotkey,
        show_error: bool = True,
    ) -> bool:
        """Register a hotkey and optionally report a conflict."""
        success = self._global_hotkey.register(hotkey)
        if not success and show_error:
            self.show_hotkey_registration_error(hotkey)
        return success

    def _show_settings_error(self, error: SettingsError) -> None:
        """Show a localized persistence error."""
        wx.MessageBox(
            format_user_error(error),
            # Translators: Title of an error saving or applying settings.
            _("Settings error"),
            wx.OK | wx.ICON_ERROR,
            self._parent,
        )
