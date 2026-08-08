"""Accessible presentation of the database file used by this process."""

from pathlib import Path

import wx

from i18n import _
from platform_support import clipboard
from platform_support.file_manager import open_containing_directory
from ui.controls import FocusableReadOnlyTextCtrl


class DatabaseLocationDialog(wx.Dialog):
    """Show the active database path and offer non-destructive actions."""

    def __init__(self, parent: wx.Window, database_file: str | Path):
        # Translators: Title of the dialog showing the database used by btText.
        super().__init__(parent, title=_("Database location"))
        self.database_file = str(Path(database_file).expanduser().resolve())
        self._create_controls()
        self.Fit()
        self.SetMinSize(self.FromDIP((560, -1)))
        self.CentreOnParent()

    def _create_controls(self) -> None:
        """Build the path field and its actions using native controls."""
        panel = wx.Panel(self)
        panel_sizer = wx.BoxSizer(wx.VERTICAL)

        # Translators: Label for the full path of the database currently open.
        label = wx.StaticText(panel, label=_("Currently used database:"))
        panel_sizer.Add(label, 0, wx.BOTTOM, self.FromDIP(6))
        self.path_field = FocusableReadOnlyTextCtrl(
            panel,
            value=self.database_file,
        )
        # Translators: Accessible name of the read-only database path field.
        self.path_field.SetName(_("Currently used database"))
        panel_sizer.Add(self.path_field, 0, wx.EXPAND)
        panel.SetSizer(panel_sizer)

        actions = wx.StdDialogButtonSizer()
        # Translators: Button that copies the displayed database path.
        self.copy_button = wx.Button(self, label=_("&Copy path"))
        # Translators: Button that opens the database's containing directory.
        self.open_folder_button = wx.Button(self, label=_("Open &folder"))
        close_button = wx.Button(self, wx.ID_CLOSE, _("&Close"))
        actions.AddButton(self.copy_button)
        actions.AddButton(self.open_folder_button)
        actions.AddButton(close_button)
        actions.Realize()

        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(panel, 1, wx.EXPAND | wx.ALL, self.FromDIP(12))
        root_sizer.Add(
            actions,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            self.FromDIP(12),
        )
        self.SetSizer(root_sizer)

        self.copy_button.Bind(wx.EVT_BUTTON, self._on_copy_path)
        self.open_folder_button.Bind(wx.EVT_BUTTON, self._on_open_folder)
        close_button.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_CLOSE))

    def _on_copy_path(self, event: wx.CommandEvent) -> None:
        """Copy the absolute database path to the Windows clipboard."""
        try:
            clipboard.copy_text(self.database_file)
        except clipboard.ClipboardError as error:
            wx.MessageBox(
                # Translators: Error shown when the database path cannot be
                # copied. {reason} is a technical system message.
                _("The database path could not be copied.\n\n{reason}").format(
                    reason=error
                ),
                # Translators: Title of an error copying the database path.
                _("Clipboard error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )

    def _on_open_folder(self, event: wx.CommandEvent) -> None:
        """Open the directory containing the active database."""
        try:
            open_containing_directory(self.database_file)
        except OSError as error:
            wx.MessageBox(
                # Translators: Error shown when the database directory cannot
                # be opened. {reason} is a technical system message.
                _("The database folder could not be opened.\n\n{reason}").format(
                    reason=error
                ),
                # Translators: Title of an error opening the database directory.
                _("Database folder error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
