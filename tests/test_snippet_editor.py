import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wx

from ui.snippet_editor import SnippetEditor


class SnippetEditorUnsavedChangesTestCase(unittest.TestCase):
    def _dialog_with_values(self, values, initial=None):
        controls = [Mock() for _value in values]
        for control, value in zip(controls, values):
            control.GetValue.return_value = value
            control.GetSelection.return_value = value
        dialog = SimpleNamespace(
            name_input=controls[0],
            category_input=controls[1],
            weight_input=controls[2],
            hotstring_input=controls[3],
            content_input=controls[4],
            _initial_state=tuple(values if initial is None else initial),
        )
        dialog._current_state = lambda: SnippetEditor._current_state(dialog)
        return dialog

    def test_unchanged_values_are_not_reported_as_unsaved(self):
        dialog = self._dialog_with_values(("Name", 1, 2, "abbr", "Content"))

        self.assertFalse(SnippetEditor._has_unsaved_changes(dialog))

    def test_each_editable_value_participates_in_change_detection(self):
        initial = ("Name", 1, 2, "abbr", "Content")

        for index, replacement in enumerate(("Other", 3, 0, "new", "Changed")):
            with self.subTest(index=index):
                current = list(initial)
                current[index] = replacement
                dialog = self._dialog_with_values(current, initial)

                self.assertTrue(SnippetEditor._has_unsaved_changes(dialog))

    def test_cancel_closes_after_discard_is_confirmed(self):
        dialog = SimpleNamespace(
            _confirm_discard_changes=Mock(return_value=True),
            _closing_allowed=False,
            EndModal=Mock(),
        )

        SnippetEditor._on_cancel(dialog, Mock())

        self.assertTrue(dialog._closing_allowed)
        dialog.EndModal.assert_called_once_with(wx.ID_CANCEL)

    def test_cancel_keeps_editor_open_when_discard_is_declined(self):
        dialog = SimpleNamespace(
            _confirm_discard_changes=Mock(return_value=False),
            _closing_allowed=False,
            EndModal=Mock(),
        )

        SnippetEditor._on_cancel(dialog, Mock())

        dialog.EndModal.assert_not_called()

    @patch("ui.snippet_editor.wx.MessageDialog")
    def test_unchanged_editor_closes_without_confirmation(self, message_dialog):
        dialog = SimpleNamespace(
            _has_unsaved_changes=lambda: False,
            _closing_allowed=False,
        )

        result = SnippetEditor._confirm_discard_changes(dialog)

        self.assertTrue(result)
        message_dialog.assert_not_called()

    @patch("ui.snippet_editor.wx.MessageDialog")
    def test_changed_editor_closes_only_after_yes(self, message_dialog):
        confirmation = message_dialog.return_value
        confirmation.ShowModal.return_value = wx.ID_YES
        dialog = SimpleNamespace(
            _has_unsaved_changes=lambda: True,
            _closing_allowed=False,
        )

        result = SnippetEditor._confirm_discard_changes(dialog)

        self.assertTrue(result)
        self.assertTrue(dialog._closing_allowed)
        confirmation.ShowModal.assert_called_once_with()
        confirmation.Destroy.assert_called_once_with()

    @patch("ui.snippet_editor.wx.MessageDialog")
    def test_already_confirmed_editor_never_asks_again(self, message_dialog):
        dialog = SimpleNamespace(
            _has_unsaved_changes=lambda: True,
            _closing_allowed=True,
        )

        result = SnippetEditor._confirm_discard_changes(dialog)

        self.assertTrue(result)
        message_dialog.assert_not_called()

    @patch("ui.snippet_editor.wx.MessageDialog")
    def test_confirmation_teardown_cannot_open_second_confirmation(
        self,
        message_dialog,
    ):
        confirmation = message_dialog.return_value
        confirmation.ShowModal.return_value = wx.ID_YES
        dialog = SimpleNamespace(
            _has_unsaved_changes=lambda: True,
            _closing_allowed=False,
            EndModal=Mock(),
        )
        confirmation.Destroy.side_effect = lambda: SnippetEditor._on_cancel(
            dialog,
            Mock(),
        )

        result = SnippetEditor._confirm_discard_changes(dialog)

        self.assertTrue(result)
        message_dialog.assert_called_once()
        dialog.EndModal.assert_not_called()

    def test_two_cancel_events_ask_only_once(self):
        dialog = SimpleNamespace(
            _confirm_discard_changes=Mock(
                side_effect=lambda: SnippetEditor._confirm_discard_changes(
                    dialog
                )
            ),
            _has_unsaved_changes=lambda: True,
            _closing_allowed=False,
            EndModal=Mock(),
        )
        with patch("ui.snippet_editor.wx.MessageDialog") as message_dialog:
            message_dialog.return_value.ShowModal.return_value = wx.ID_YES

            SnippetEditor._on_cancel(dialog, Mock())
            SnippetEditor._on_cancel(dialog, Mock())

        message_dialog.assert_called_once()
        dialog.EndModal.assert_called_once_with(wx.ID_CANCEL)
