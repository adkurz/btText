import wx
import pymitter

import app_paths
import info
import ui
from datamodel import DataModel

def main():
    ee = pymitter.EventEmitter()
    model = DataModel(ee, app_paths.get_database_file())
    try:
        app = wx.App()
        app.SetAppName(info.name)
        frame = ui.MainFrame(ee, model)
        frame.Show()
        app.MainLoop()
    finally:
        model.close()

if __name__ == '__main__':
    main()
