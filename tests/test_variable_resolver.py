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
