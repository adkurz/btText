import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from core.variables import RenderedSnippet, UnknownVariableError
from ui.variable_resolver import SnippetVariableResolver, show_variable_error


class SnippetVariableResolverTestCase(unittest.TestCase):
    def test_timestamp_and_locale_are_captured_once_per_rendering(self):
        timestamp = datetime(2026, 8, 6, 14, 35, tzinfo=timezone.utc)
        get_timestamp = Mock(return_value=timestamp)
        get_locale = Mock(return_value="de")
        engine = Mock()
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
