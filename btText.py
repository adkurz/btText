"""Application entry point and top-level resource lifetime management."""

import wx
import pymitter

import app_paths
import datamodel
from app_settings import AppSettings, SettingsError, SettingsStore
from error_messages import format_user_error
import i18n
from i18n import _
import info
import ui
from datamodel import DataModel

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
        try:
            model = DataModel(ee, app_paths.get_database_file())
        except datamodel.DataModelError as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Title of a fatal startup error concerning the
                # snippet database.
                _("Database error"),
                wx.OK | wx.ICON_ERROR,
            )
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
