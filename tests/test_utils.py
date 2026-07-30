import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import wx

from ui.utils import YesNoConfirmationDialog


class YesNoConfirmationDialogTestCase(unittest.TestCase):
    def test_no_handler_ends_dialog_with_no(self):
        dialog = SimpleNamespace(EndModal=Mock())

        YesNoConfirmationDialog._on_no(dialog, Mock())

        dialog.EndModal.assert_called_once_with(wx.ID_NO)

    def test_yes_handler_ends_dialog_with_yes(self):
        dialog = SimpleNamespace(EndModal=Mock())

        YesNoConfirmationDialog._on_yes(dialog, Mock())

        dialog.EndModal.assert_called_once_with(wx.ID_YES)
