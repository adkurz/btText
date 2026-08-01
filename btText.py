"""Application entry point and top-level resource lifetime management."""

import dataclasses

import wx
import pymitter

from platform_support import app_paths
from core import datamodel
from core.app_settings import AppSettings, SettingsError, SettingsStore
from core.error_messages import format_user_error
import i18n
from i18n import _
import info
import ui
from ui import theme
from core.datamodel import DataModel
from ui.database_selection import select_database


def _open_database(ee, settings_store, settings):
    """Resolve, open, and when needed persist the startup database."""
    default_database_file = app_paths.get_database_file()
    if settings.database_file is not None:
        initial_path = settings.database_file
        allow_create = False
        persist_path = False
    elif default_database_file.exists():
        initial_path = default_database_file
        allow_create = False
        persist_path = True
    else:
        # Do not search other locations or move data automatically. In
        # particular, an installed build cannot reliably identify which
        # portable directory (if any) the user previously used.
        initial_path = None
        allow_create = False
        persist_path = False

    while True:
        if initial_path is None:
            selection = select_database(None, first_start=True)
            if selection is None:
                return None, settings
            initial_path = selection.path
            allow_create = selection.create
            persist_path = True
        try:
            model = DataModel(
                ee,
                initial_path,
                allow_create=allow_create,
            )
        except datamodel.DataModelError as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Title for an error opening a selected snippet
                # database.
                _("Database error"),
                wx.OK | wx.ICON_ERROR,
            )
            initial_path = None
            continue

        if persist_path:
            new_settings = dataclasses.replace(
                settings,
                database_file=str(initial_path),
            )
            try:
                settings_store.save(new_settings)
            except SettingsError as error:
                model.close()
                wx.MessageBox(
                    format_user_error(error),
                    # Translators: Title for an error saving the selected
                    # database path in the application settings.
                    _("Settings error"),
                    wx.OK | wx.ICON_ERROR,
                )
                return None, settings
            settings = new_settings
        return model, settings

def main():
    """Initialize the wx application and release resources on shutdown."""
    ee = pymitter.EventEmitter()
    instance_checker = None
    model = None
    try:
        app = wx.App()
        app.SetAppName(info.name)
        instance_checker = wx.SingleInstanceChecker(
            f"{info.name}-{wx.GetUserId()}"
        )
        another_instance_running = instance_checker.IsAnotherRunning()
        settings_store = SettingsStore(
            app_paths.get_settings_file(),
            app_paths.get_locale_directory(),
        )
        settings_error = None
        try:
            settings = settings_store.load()
        except SettingsError as error:
            settings = AppSettings()
            settings_error = error
        theme.initialize(settings.appearance)
        theme.apply_to_app(app)
        language_error = None
        try:
            i18n.initialize(
                settings.language,
                app_paths.get_locale_directory(),
                wx,
            )
        except i18n.LanguageError as error:
            language_error = error
        if another_instance_running:
            wx.MessageBox(
                # Translators: Information shown when the user tries to start
                # the application while it is already running.
                _("btText is already running."),
                info.name,
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        model, settings = _open_database(ee, settings_store, settings)
        if model is None:
            return
        frame = ui.MainFrame(ee, model, settings_store, settings)
        if settings_error is not None:
            wx.MessageBox(
                format_user_error(settings_error),
                # Translators: Title of a startup warning concerning settings.
                _("Settings error"),
                wx.OK | wx.ICON_ERROR,
                frame,
            )
        if language_error is not None:
            wx.MessageBox(
                format_user_error(language_error),
                # Translators: Title of a startup warning after a translation
                # catalog could not be loaded.
                _("Language error"),
                wx.OK | wx.ICON_ERROR,
                frame,
            )
        app.MainLoop()
    finally:
        if model is not None:
            model.close()

if __name__ == '__main__':
    main()
