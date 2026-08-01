import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import wx

from ui.database_selection import select_database


class DatabaseSelectionTestCase(unittest.TestCase):
    @patch("ui.database_selection.app_paths.get_database_file")
    @patch("ui.database_selection.wx.FileDialog")
    @patch("ui.database_selection.wx.MessageDialog")
    def test_create_dialog_suggests_default_database_path(
        self,
        message_dialog_class,
        file_dialog_class,
        get_database_file,
    ):
        default_database_file = Path("C:/btText/data.db")
        get_database_file.return_value = default_database_file
        message_dialog = Mock()
        message_dialog.ShowModal.return_value = wx.ID_YES
        message_dialog_class.return_value = message_dialog
        file_dialog = Mock()
        file_dialog.ShowModal.return_value = wx.ID_CANCEL
        file_dialog_class.return_value = file_dialog

        self.assertIsNone(select_database(None))

        file_dialog_class.assert_called_once_with(
            None,
            unittest.mock.ANY,
            wildcard=unittest.mock.ANY,
            style=wx.FD_SAVE,
            defaultDir=str(default_database_file.parent),
            defaultFile="data.db",
        )


if __name__ == "__main__":
    unittest.main()
