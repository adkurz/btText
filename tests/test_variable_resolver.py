import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import wx

from core.variables import (
    RenderedSnippet,
    ResolutionPlan,
    UnknownVariableError,
    VariableRenderingCancelled,
)
from ui.variable_resolver import SnippetVariableResolver, show_variable_error


class SnippetVariableResolverTestCase(unittest.TestCase):
    @patch("ui.variable_resolver.i18n.get_formatting_locale", return_value="fr_FR")
    def test_default_locale_uses_the_formatting_locale(self, get_locale):
        engine = Mock()
        engine.plan.return_value = ResolutionPlan()
        engine.render.return_value = RenderedSnippet("resolved")
        resolver = SnippetVariableResolver(engine)

        resolver.render("{{date}}")

        context = engine.render.call_args.args[1]
        self.assertEqual(context.locale, "fr_FR")
        get_locale.assert_called_once_with()

    def test_timestamp_and_locale_are_captured_once_per_rendering(self):
        timestamp = datetime(2026, 8, 6, 14, 35, tzinfo=timezone.utc)
        get_timestamp = Mock(return_value=timestamp)
        get_locale = Mock(return_value="de")
        engine = Mock()
        engine.plan.return_value = ResolutionPlan()
        engine.render.return_value = RenderedSnippet("resolved")
        resolver = SnippetVariableResolver(
            engine,
            get_timestamp=get_timestamp,
            get_locale=get_locale,
        )

        result = resolver.render("{{date}} {{time}}")

        self.assertEqual(result, RenderedSnippet("resolved"))
        get_timestamp.assert_called_once_with()
        get_locale.assert_called_once_with()
        context = engine.render.call_args.args[1]
        self.assertEqual(context.timestamp, timestamp)
        self.assertEqual(context.locale, "de")

    def test_default_timestamp_is_timezone_aware(self):
        timestamp = SnippetVariableResolver._current_timestamp()

        self.assertIsNotNone(timestamp.tzinfo)
        self.assertIsNotNone(timestamp.utcoffset())

    def test_validation_does_not_read_runtime_context(self):
        engine = Mock()
        engine.plan.return_value = ResolutionPlan()
        resolver = SnippetVariableResolver(engine)

        with (
            patch("ui.variable_resolver.clipboard.read_text") as read_text,
            patch(
                "ui.variable_resolver.windows.get_window_application_name"
            ) as get_application_name,
        ):
            resolver.validate("{{clipboard}} {{app}}")

        engine.validate.assert_called_once_with("{{clipboard}} {{app}}")
        read_text.assert_not_called()
        get_application_name.assert_not_called()

    def test_context_values_are_lazy_and_memoized_per_rendering(self):
        engine = Mock()
        engine.plan.return_value = ResolutionPlan()

        def render(_template, context):
            return RenderedSnippet(
                context.get_clipboard_text()
                + context.get_clipboard_text()
                + context.get_application_name()
                + context.get_application_name()
            )

        engine.render.side_effect = render
        resolver = SnippetVariableResolver(engine)
        with (
            patch(
                "ui.variable_resolver.clipboard.read_text",
                return_value="clip",
            ) as read_text,
            patch(
                "ui.variable_resolver.windows.get_window_application_name",
                return_value="notepad.exe",
            ) as get_application_name,
        ):
            result = resolver.render("template", target_window=42)

        self.assertEqual(result.text, "clipclipnotepad.exenotepad.exe")
        read_text.assert_called_once_with()
        get_application_name.assert_called_once_with(42)

    def test_all_distinct_input_labels_are_requested_together(self):
        engine = Mock()
        engine.plan.return_value = ResolutionPlan(
            ("Customer number", "Reference"),
        )

        def render(_template, context):
            return RenderedSnippet(
                context.request_input("Customer number")
                + context.request_input("Reference")
            )

        engine.render.side_effect = render
        request_inputs = Mock(
            return_value={"Customer number": "42", "Reference": "A7"}
        )
        resolver = SnippetVariableResolver(engine, request_inputs=request_inputs)

        result = resolver.render("template")

        self.assertEqual(result.text, "42A7")
        request_inputs.assert_called_once_with(("Customer number", "Reference"))

    @patch("ui.variable_resolver.InteractiveVariablesDialog")
    def test_input_dialog_returns_all_values_and_is_destroyed(self, dialog_class):
        dialog = dialog_class.return_value
        dialog.ShowModal.return_value = wx.ID_OK
        dialog.get_values.return_value = {
            "Customer number": "42",
            "Reference": "A7",
        }
        parent = Mock()
        resolver = SnippetVariableResolver(Mock(), parent=parent)

        result = resolver._show_input_dialog(("Customer number", "Reference"))

        self.assertEqual(
            result,
            {"Customer number": "42", "Reference": "A7"},
        )
        dialog_class.assert_called_once_with(
            parent,
            ("Customer number", "Reference"),
        )
        dialog.Destroy.assert_called_once_with()

    @patch("ui.variable_resolver.InteractiveVariablesDialog")
    def test_cancelled_input_dialog_returns_none(self, dialog_class):
        dialog = dialog_class.return_value
        dialog.ShowModal.return_value = wx.ID_CANCEL
        resolver = SnippetVariableResolver(Mock())

        self.assertIsNone(resolver._show_input_dialog(("Customer number",)))

        dialog.get_values.assert_not_called()
        dialog.Destroy.assert_called_once_with()

    def test_cancelled_combined_input_dialog_cancels_before_rendering(self):
        engine = Mock()
        engine.plan.return_value = ResolutionPlan(("Customer number",))
        resolver = SnippetVariableResolver(
            engine,
            request_inputs=Mock(return_value=None),
        )

        with self.assertRaises(VariableRenderingCancelled):
            resolver.render("{{input:Customer number}}")

        engine.render.assert_not_called()

    @patch("ui.variable_resolver.wx.MessageBox")
    def test_variable_errors_are_formatted_at_one_ui_boundary(self, message_box):
        parent = Mock()
        error = UnknownVariableError(
            "variable_unknown",
            "Unknown variable {name}",
            name="missing",
            position=0,
        )

        show_variable_error(parent, error)

        message_box.assert_called_once()
        self.assertEqual(message_box.call_args.args[3], parent)


if __name__ == "__main__":
    unittest.main()
