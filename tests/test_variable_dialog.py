import unittest

import wx

from core.builtin_variables import (
    BUILTIN_VARIABLE_CATALOG,
    VariableEditorKind,
)
from ui.variable_dialog import (
    InteractiveVariablesDialog,
    VariablePickerDialog,
    VariablePreviewDialog,
    VariableSuggestion,
    get_builtin_variable_suggestions,
)


class VariableDialogTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def test_builtin_catalog_contains_every_supported_expression(self):
        suggestions = get_builtin_variable_suggestions()
        expressions = {suggestion.expression for suggestion in suggestions}

        expected_count = 0
        for variable in BUILTIN_VARIABLE_CATALOG:
            name = variable.definition.name
            if variable.editor_kind is VariableEditorKind.INPUT_LABEL:
                self.assertIn(
                    "{{" + name + ":" + variable.editor_placeholder + "}}",
                    expressions,
                )
                expected_count += 1
            else:
                self.assertIn("{{" + name + "}}", expressions)
                expected_count += 1 + len(variable.editor_options)
                for option in variable.editor_options:
                    self.assertIn(
                        "{{" + name + ":" + option + "}}",
                        expressions,
                    )

        self.assertEqual(len(suggestions), expected_count)

    def test_picker_splits_variables_and_formats_into_two_lists(self):
        suggestions = (
            VariableSuggestion("{{date}}", "Current date, default format."),
            VariableSuggestion("{{date:iso}}", "Current date, ISO format."),
            VariableSuggestion("{{app}}", "Target application."),
        )
        dialog = VariablePickerDialog(None, suggestions)
        try:
            self.assertEqual(dialog.variable_list.GetCount(), 2)
            self.assertIn("Current date", dialog.variable_list.GetString(0))
            self.assertTrue(dialog.settings_panel.IsShown())
            self.assertEqual(dialog.settings_list.GetCount(), 2)
            self.assertEqual(dialog.get_selected_expression(), "{{date}}")
            dialog.settings_list.SetSelection(1)
            self.assertEqual(dialog.get_selected_expression(), "{{date:iso}}")
            self.assertTrue(dialog.insert_button.IsEnabled())
        finally:
            dialog.Destroy()

    def test_picker_hides_settings_for_variable_without_options(self):
        suggestions = get_builtin_variable_suggestions()
        dialog = VariablePickerDialog(None, suggestions)
        try:
            app_index = next(
                index
                for index in range(dialog.variable_list.GetCount())
                if dialog.variable_list.GetString(index).startswith("{{app}}")
            )
            dialog.variable_list.SetSelection(app_index)
            dialog._update_settings()

            self.assertFalse(dialog.settings_panel.IsShown())
            self.assertEqual(dialog.settings_list.GetCount(), 0)
            self.assertEqual(dialog.get_selected_expression(), "{{app}}")
        finally:
            dialog.Destroy()

    def test_picker_builds_input_expression_from_entered_prompt(self):
        dialog = VariablePickerDialog(None, get_builtin_variable_suggestions())
        try:
            input_index = next(
                index
                for index in range(dialog.variable_list.GetCount())
                if dialog.variable_list.GetString(index).startswith("{{input}}")
            )
            dialog.variable_list.SetSelection(input_index)
            dialog._update_settings()

            self.assertTrue(dialog.settings_panel.IsShown())
            self.assertTrue(dialog.input_text.IsShown())
            self.assertFalse(dialog.settings_list.IsShown())
            self.assertFalse(dialog.insert_button.IsEnabled())

            dialog.input_text.SetValue("Kundennummer")

            self.assertTrue(dialog.insert_button.IsEnabled())
            self.assertEqual(
                dialog.get_selected_expression(),
                "{{input:Kundennummer}}",
            )
        finally:
            dialog.Destroy()

    def test_empty_picker_disables_insertion(self):
        dialog = VariablePickerDialog(None, ())
        try:
            self.assertIsNone(dialog.get_selected_expression())
            self.assertFalse(dialog.insert_button.IsEnabled())
        finally:
            dialog.Destroy()

    def test_preview_is_read_only_and_preserves_rendered_text(self):
        dialog = VariablePreviewDialog(None, "First line\r\nSecond line")
        try:
            self.assertEqual(
                dialog.preview_text.GetValue(),
                "First line\nSecond line",
            )
            self.assertFalse(dialog.preview_text.IsEditable())
            self.assertTrue(dialog.preview_text.AcceptsFocusFromKeyboard())
        finally:
            dialog.Destroy()

    def test_interactive_dialog_collects_all_values_in_label_order(self):
        dialog = InteractiveVariablesDialog(
            None,
            ("Kundennummer", "Referenz"),
        )
        try:
            dialog._inputs["Kundennummer"].SetValue("42")
            dialog._inputs["Referenz"].SetValue("")

            self.assertEqual(
                dialog.get_values(),
                {"Kundennummer": "42", "Referenz": ""},
            )
            self.assertEqual(
                dialog._inputs["Kundennummer"].GetName(),
                "Kundennummer",
            )
        finally:
            dialog.Destroy()

    def test_interactive_dialog_requires_at_least_one_label(self):
        with self.assertRaises(ValueError):
            InteractiveVariablesDialog(None, ())


if __name__ == "__main__":
    unittest.main()
