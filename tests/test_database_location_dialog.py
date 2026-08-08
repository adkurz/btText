import unittest
from pathlib import Path
from unittest.mock import patch

import wx

from platform_support import clipboard
from ui.database_location_dialog import DatabaseLocationDialog


class DatabaseLocationDialogTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def setUp(self):
        self.database_file = Path("database folder/data.db").resolve()
        self.dialog = DatabaseLocationDialog(None, self.database_file)

    def tearDown(self):
        self.dialog.Destroy()

    def test_displays_absolute_path_in_focusable_read_only_field(self):
        self.assertEqual(self.dialog.path_field.GetValue(), str(self.database_file))
        self.assertTrue(self.dialog.path_field.IsEditable() is False)
        self.assertTrue(self.dialog.path_field.AcceptsFocusFromKeyboard())

    @patch("ui.database_location_dialog.clipboard.copy_text")
    def test_copy_button_copies_database_path(self, copy_text):
        self.dialog._on_copy_path(wx.CommandEvent())

        copy_text.assert_called_once_with(str(self.database_file))

    @patch("ui.database_location_dialog.wx.MessageBox")
    @patch(
        "ui.database_location_dialog.clipboard.copy_text",
        side_effect=clipboard.ClipboardError("busy"),
    )
    def test_copy_error_is_reported(self, copy_text, message_box):
        self.dialog._on_copy_path(wx.CommandEvent())

        message_box.assert_called_once()

    @patch("ui.database_location_dialog.open_containing_directory")
    def test_open_folder_button_opens_database_directory(self, open_directory):
        self.dialog._on_open_folder(wx.CommandEvent())

        open_directory.assert_called_once_with(str(self.database_file))
