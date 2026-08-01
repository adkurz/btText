"""Accessible file selection for creating or opening snippet databases."""

import dataclasses
from pathlib import Path

import wx

from i18n import _
from platform_support import app_paths
from ui import utils


@dataclasses.dataclass(frozen=True)
class DatabaseSelection:
    """A database path together with whether it should be newly created."""

    path: Path
    create: bool


def select_database(
    parent: wx.Window | None,
    *,
    first_start: bool = False,
) -> DatabaseSelection | None:
    """Ask whether to create or open a database, then select its path."""
    message = (
        # Translators: First-start question offering to create a new snippet
        # database or open one that already exists.
        _(
            "Welcome to btText. Would you like to create a new database "
            "or open an existing database?"
        )
        if first_start
        # Translators: Question shown when changing the snippet database.
        else _(
            "Would you like to create a new database or open an existing "
            "database?"
        )
    )
    with utils.managed_dialog(
        wx.MessageDialog(
            parent,
            message,
            # Translators: Title of the database creation/opening choice.
            _("Select database"),
            wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
        )
    ) as dialog:
        dialog.SetYesNoCancelLabels(
            # Translators: Button that continues with a Save dialog for a new
            # snippet database.
            _("Create &new database..."),
            # Translators: Button that continues with an Open dialog for an
            # existing snippet database.
            _("&Open existing database..."),
            # Translators: Button that cancels database selection.
            _("&Cancel"),
        )
        result = dialog.ShowModal()
    if result == wx.ID_CANCEL:
        return None

    create = result == wx.ID_YES
    style = wx.FD_SAVE if create else wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
    title = (
        # Translators: Title of the file dialog used to create a database.
        _("Create new database")
        if create
        # Translators: Title of the file dialog used to open a database.
        else _("Open existing database")
    )
    file_dialog_arguments = {}
    if create:
        default_database_file = app_paths.get_database_file()
        file_dialog_arguments = {
            "defaultDir": str(default_database_file.parent),
            "defaultFile": default_database_file.name,
        }
    with utils.managed_dialog(
        wx.FileDialog(
            parent,
            title,
            # Translators: File-dialog filter. Preserve the vertical bars,
            # wildcard patterns, and .db extension.
            wildcard=_("btText databases (*.db)|*.db|All files (*.*)|*.*"),
            style=style,
            **file_dialog_arguments,
        )
    ) as dialog:
        if dialog.ShowModal() != wx.ID_OK:
            return None
        path = Path(dialog.GetPath()).resolve()

    if create and path.exists():
        wx.MessageBox(
            # Translators: Error after choosing an existing file while the user
            # requested creation of a new database.
            _("The selected file already exists. Choose a different name."),
            # Translators: Title for a failed database selection or creation.
            _("Database error"),
            wx.OK | wx.ICON_ERROR,
            parent,
        )
        return select_database(parent, first_start=first_start)
    return DatabaseSelection(path, create)
