import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import wx

from ui.utils import YesNoConfirmationDialog, frozen, popup_menu


class NativeResourceHelperTestCase(unittest.TestCase):
    def test_frozen_thaws_window_after_an_error(self):
        window = Mock()

        with self.assertRaisesRegex(RuntimeError, "update failed"):
            with frozen(window):
                raise RuntimeError("update failed")

        window.Freeze.assert_called_once_with()
        window.Thaw.assert_called_once_with()

    def test_popup_menu_destroys_menu_after_an_error(self):
        window = Mock()
        menu = Mock()
        window.PopupMenu.side_effect = RuntimeError("popup failed")

        with self.assertRaisesRegex(RuntimeError, "popup failed"):
            popup_menu(window, menu)

        window.PopupMenu.assert_called_once_with(menu)
        menu.Destroy.assert_called_once_with()


class YesNoConfirmationDialogTestCase(unittest.TestCase):
    def test_no_handler_ends_dialog_with_no(self):
        dialog = SimpleNamespace(EndModal=Mock())

        YesNoConfirmationDialog._on_no(dialog, Mock())

        dialog.EndModal.assert_called_once_with(wx.ID_NO)

    def test_yes_handler_ends_dialog_with_yes(self):
        dialog = SimpleNamespace(EndModal=Mock())

        YesNoConfirmationDialog._on_yes(dialog, Mock())

        dialog.EndModal.assert_called_once_with(wx.ID_YES)
