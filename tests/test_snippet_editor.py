import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wx

from core import datamodel
from core.events import EventEmitter
from core.variables import RenderedSnippet, UnknownVariableError
from ui.snippet_editor import SnippetEditor
from ui.variable_dialog import get_builtin_variable_suggestions


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

    @patch("ui.snippet_editor.utils.confirm_yes_no")
    def test_unchanged_editor_closes_without_confirmation(self, confirm_yes_no):
        dialog = SimpleNamespace(
            _has_unsaved_changes=lambda: False,
            _closing_allowed=False,
        )

        result = SnippetEditor._confirm_discard_changes(dialog)

        self.assertTrue(result)
        confirm_yes_no.assert_not_called()

    @patch("ui.snippet_editor.utils.confirm_yes_no", return_value=True)
    def test_changed_editor_closes_only_after_yes(self, confirm_yes_no):
        dialog = SimpleNamespace(
            _has_unsaved_changes=lambda: True,
            _closing_allowed=False,
        )

        result = SnippetEditor._confirm_discard_changes(dialog)

        self.assertTrue(result)
        self.assertTrue(dialog._closing_allowed)
        confirm_yes_no.assert_called_once()
        self.assertTrue(confirm_yes_no.call_args.kwargs["warning"])

    @patch("ui.snippet_editor.utils.confirm_yes_no")
    def test_already_confirmed_editor_never_asks_again(self, confirm_yes_no):
        dialog = SimpleNamespace(
            _has_unsaved_changes=lambda: True,
            _closing_allowed=True,
        )

        result = SnippetEditor._confirm_discard_changes(dialog)

        self.assertTrue(result)
        confirm_yes_no.assert_not_called()

    def test_two_cancel_events_ask_only_once(self):
        dialog = SimpleNamespace(
            _confirm_discard_changes=Mock(
                side_effect=lambda: SnippetEditor._confirm_discard_changes(dialog)
            ),
            _has_unsaved_changes=lambda: True,
            _closing_allowed=False,
            EndModal=Mock(),
        )
        with patch(
            "ui.snippet_editor.utils.confirm_yes_no",
            return_value=True,
        ) as confirm_yes_no:

            SnippetEditor._on_cancel(dialog, Mock())
            SnippetEditor._on_cancel(dialog, Mock())

        confirm_yes_no.assert_called_once()
        dialog.EndModal.assert_called_once_with(wx.ID_CANCEL)


class SnippetEditorVariableTestCase(unittest.TestCase):
    def test_expression_replaces_selection_and_restores_content_focus(self):
        content_input = Mock()
        content_input.GetSelection.return_value = (6, 10)
        dialog = SimpleNamespace(content_input=content_input)

        SnippetEditor._insert_expression(dialog, "{{date:long}}")

        content_input.Replace.assert_called_once_with(6, 10, "{{date:long}}")
        content_input.SetInsertionPoint.assert_called_once_with(19)
        content_input.SetFocus.assert_called_once_with()

    def test_rendering_error_is_shown_at_shared_ui_boundary(self):
        error = UnknownVariableError(
            "variable_unknown",
            "Unknown variable {name}",
            name="missing",
            position=0,
        )
        dialog = SimpleNamespace(_render_snippet=Mock(side_effect=error))

        with patch("ui.snippet_editor.show_variable_error") as show_error:
            result = SnippetEditor._render_variables(dialog, "{{missing}}")

        self.assertIsNone(result)
        show_error.assert_called_once_with(dialog, error)

    def _save_dialog(self, variables_are_valid):
        model = Mock()
        dialog = SimpleNamespace(
            Validate=Mock(return_value=True),
            name_input=Mock(GetValue=Mock(return_value="Greeting")),
            category_input=Mock(GetSelection=Mock(return_value=0)),
            _categories=[SimpleNamespace(id=7)],
            weight_input=Mock(GetSelection=Mock(return_value=1)),
            content_input=Mock(
                GetValue=Mock(return_value="Today is {{date:long}}.")
            ),
            hotstring_input=Mock(GetValue=Mock(return_value="dated")),
            _variables_are_valid=Mock(return_value=variables_are_valid),
            _model=model,
            _snippet=None,
            _closing_allowed=False,
            EndModal=Mock(),
        )
        return dialog, model

    def test_save_stops_before_model_write_when_variables_are_invalid(self):
        dialog, model = self._save_dialog(None)

        SnippetEditor.save(dialog, Mock())

        dialog._variables_are_valid.assert_called_once_with(
            "Today is {{date:long}}."
        )
        dialog.content_input.SetFocus.assert_called_once_with()
        model.add_snippet.assert_not_called()
        dialog.EndModal.assert_not_called()

    def test_save_validates_but_persists_the_original_template(self):
        dialog, model = self._save_dialog(True)

        SnippetEditor.save(dialog, Mock())

        saved_snippet = model.add_snippet.call_args.args[0]
        self.assertEqual(saved_snippet.content, "Today is {{date:long}}.")
        self.assertEqual(saved_snippet.category_id, 7)
        self.assertEqual(saved_snippet.weight, 2)
        self.assertEqual(saved_snippet.hotstring, "dated")
        self.assertTrue(dialog._closing_allowed)
        dialog.EndModal.assert_called_once_with(wx.OK)

    @patch("ui.snippet_editor.VariablePreviewDialog")
    @patch("ui.snippet_editor.utils.managed_dialog")
    def test_preview_displays_resolved_text(self, managed_dialog, preview_class):
        preview = Mock()
        preview_class.return_value = preview
        managed_dialog.return_value.__enter__.return_value = preview
        dialog = SimpleNamespace(
            content_input=Mock(GetValue=Mock(return_value="{{date}}")),
            _render_variables=Mock(return_value=RenderedSnippet("06.08.26")),
        )

        SnippetEditor._on_preview(dialog, Mock())

        preview_class.assert_called_once_with(dialog, "06.08.26")
        preview.ShowModal.assert_called_once_with()


class SnippetEditorConstructionTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def test_real_editor_constructs_variable_actions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            model = datamodel.DataModel(
                EventEmitter(),
                Path(temporary_directory) / "data.db",
            )
            category = model.add_category(datamodel.Category("General"))
            dialog = None
            try:
                dialog = SnippetEditor(
                    None,
                    model.ee,
                    model,
                    category.id,
                    lambda text: RenderedSnippet(text),
                    lambda text: None,
                    get_builtin_variable_suggestions(),
                )

                self.assertIsInstance(dialog.content_input, wx.TextCtrl)
                self.assertTrue(dialog.insert_variable_button.IsEnabled())
                self.assertTrue(dialog.preview_button.IsEnabled())
                self.assertEqual(
                    dialog.content_input.GetWindowStyle() & wx.TE_MULTILINE,
                    wx.TE_MULTILINE,
                )
            finally:
                if dialog is not None:
                    dialog.Destroy()
                model.close()
