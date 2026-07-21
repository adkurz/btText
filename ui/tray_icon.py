from typing import TYPE_CHECKING

import wx
import wx.adv

import app_paths
import info

if TYPE_CHECKING:
    from ui.main_frame import MainFrame


class TrayIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame: "MainFrame"):
        super().__init__()
        self._frame = frame
        icon = wx.Icon(wx.Bitmap(str(app_paths.get_icon_file())))
        self.SetIcon(
            icon,
            "{app_name} - {app_version}".format(
                app_name=info.name,
                app_version=info.version,
            ),
        )  # type: ignore
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_left_click)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        restore = menu.Append(wx.ID_ANY, "Show snippets")
        self.Bind(wx.EVT_MENU, self.on_restore, restore)
        exit_item = menu.Append(wx.ID_EXIT, "Exit")
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        return menu

    def on_left_click(self, event: wx.Event):
        self.on_restore(event)

    def on_restore(self, event: wx.Event):
        self._frame.show_and_focus()

    def on_exit(self, event):
        self._frame.allow_close = True
        self._frame.Close()
