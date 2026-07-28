"""System-tray commands for restoring or exiting the application."""

from typing import TYPE_CHECKING

import wx
import wx.adv

import app_paths
import datamodel
import info
from i18n import _

if TYPE_CHECKING:
    from ui.main_frame import MainFrame


class TrayIcon(wx.adv.TaskBarIcon):
    """Keep the hidden main window accessible from the notification area."""
    def __init__(self, frame: "MainFrame"):
        """Create the tray icon associated with the main frame."""
        super().__init__()
        self._frame = frame
        icon = wx.Icon(wx.Bitmap(str(app_paths.get_icon_file())))
        self.SetIcon(
            icon,
            # Translators: Notification-area tooltip identifying the running
            # application. Keep the application name and version placeholders.
            _("{app_name} {app_version}").format(
                app_name=info.name,
                app_version=info.version,
            ),
        )  # type: ignore
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_left_click)

    def CreatePopupMenu(self):
        """Build the tray menu on demand as required by wxPython."""
        menu = wx.Menu()
        # Translators: Notification-area menu command that restores and focuses
        # btText's main window.
        restore = menu.Append(wx.ID_ANY, _("Show snippets"))
        self.Bind(wx.EVT_MENU, self.on_restore, restore)
        # Translators: Notification-area menu command that closes btText.
        exit_item = menu.Append(wx.ID_EXIT, _("Exit"))
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        return menu

    def on_left_click(self, event: wx.Event):
        """Restore the main window after a left click."""
        self.on_restore(event)

    def on_restore(self, event: wx.Event):
        """Restore and focus the main window."""
        self._frame.show_and_focus()

    def on_exit(self, event):
        """Allow and request a real application shutdown."""
        self._frame.on_exit_application(event)

    def show_hotstring_notification(self, snippet: datamodel.Snippet) -> None:
        """Confirm one automatic expansion through the Windows shell."""
        self.ShowBalloon(
            info.name,
            # Translators: Windows notification after a hotstring expansion.
            # {hotstring} is the typed abbreviation and {snippet} is the name of
            # the inserted snippet; the snippet content is deliberately omitted.
            _("Hotstring “{hotstring}” expanded to “{snippet}”.").format(
                hotstring=snippet.hotstring,
                snippet=snippet.name,
            ),
            3000,
            wx.ICON_INFORMATION,
        )
