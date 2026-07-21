import wx
import pymitter

import app_paths
from app_settings import AppSettings, SettingsError, SettingsStore
import info
import ui
from datamodel import DataModel

def main():
    ee = pymitter.EventEmitter()
    model = DataModel(ee, app_paths.get_database_file())
    try:
        app = wx.App()
        app.SetAppName(info.name)
        settings_store = SettingsStore(app_paths.get_settings_file())
        settings_error = None
        try:
            settings = settings_store.load()
        except SettingsError as error:
            settings = AppSettings()
            settings_error = error
        frame = ui.MainFrame(ee, model, settings_store, settings)
        if settings_error is not None:
            wx.MessageBox(
                str(settings_error),
                "Settings error",
                wx.OK | wx.ICON_ERROR,
                frame,
            )
        app.MainLoop()
    finally:
        model.close()

if __name__ == '__main__':
    main()
