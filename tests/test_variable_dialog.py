import unittest

import wx

from core.builtin_variables import (
    BUILTIN_VARIABLE_FORMATS,
    BUILTIN_VARIABLE_NAMES,
    CONTEXT_VARIABLE_NAMES,
    TEMPORAL_VARIABLE_NAMES,
)
from ui.variable_dialog import (
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

        self.assertEqual(len(suggestions), 20)
        for name in BUILTIN_VARIABLE_NAMES:
            self.assertIn("{{" + name + "}}", expressions)
        for name in TEMPORAL_VARIABLE_NAMES:
            for format_name in BUILTIN_VARIABLE_FORMATS:
                self.assertIn(
                    "{{" + name + ":" + format_name + "}}",
                    expressions,
                )
        for name in CONTEXT_VARIABLE_NAMES:
            self.assertFalse(
                any(expression.startswith("{{" + name + ":") for expression in expressions)
            )

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


if __name__ == "__main__":
    unittest.main()
