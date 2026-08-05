import unittest
from datetime import datetime, timezone

from core.builtin_variables import create_builtin_variable_engine
from core.variables import (
    RenderedSnippet,
    ResolutionContext,
    VariableRenderingCancelled,
    VariableResolutionError,
)


class BuiltinVariableTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_builtin_variable_engine()
        self.timestamp = datetime(
            2026,
            8,
            6,
            14,
            35,
            27,
            tzinfo=timezone.utc,
        )

    def render(
        self,
        template,
        locale="de",
        get_clipboard_text=None,
        get_application_name=None,
        request_input=None,
    ):
        return self.engine.render(
            template,
            ResolutionContext(
                self.timestamp,
                locale,
                get_clipboard_text,
                get_application_name,
                request_input,
            ),
        ).text

    def test_date_defaults_to_localized_short_format(self):
        self.assertEqual(self.render("{{date}}", "de"), "06.08.26")
        self.assertEqual(self.render("{{date}}", "en"), "8/6/26")

    def test_named_date_formats_follow_the_context_locale(self):
        expected = {
            "short": "06.08.26",
            "medium": "06.08.2026",
            "long": "6. August 2026",
            "full": "Donnerstag, 6. August 2026",
        }

        for format_name, value in expected.items():
            with self.subTest(format=format_name):
                self.assertEqual(
                    self.render("{{date:" + format_name + "}}"),
                    value,
                )

    def test_time_uses_localized_cldr_formats(self):
        self.assertEqual(self.render("{{time:short}}", "de"), "14:35")
        self.assertEqual(self.render("{{time:medium}}", "de"), "14:35:27")
        self.assertEqual(self.render("{{time:short}}", "en"), "2:35\u202fPM")

    def test_datetime_uses_one_localized_combined_format(self):
        self.assertEqual(
            self.render("{{datetime:long}}", "de"),
            "6. August 2026, 14:35:27 UTC",
        )
        self.assertEqual(
            self.render("{{datetime:long}}", "en"),
            "August 6, 2026, 2:35:27\u202fPM UTC",
        )

    def test_iso_formats_are_locale_independent(self):
        template = "{{date:iso}}|{{time:iso}}|{{datetime:iso}}"
        expected = (
            "2026-08-06|14:35:27+00:00|2026-08-06T14:35:27+00:00"
        )

        self.assertEqual(self.render(template, "de"), expected)
        self.assertEqual(self.render(template, "en"), expected)

    def test_unknown_format_is_rejected(self):
        with self.assertRaises(VariableResolutionError) as raised:
            self.render("{{date:verbose}}")

        self.assertEqual(raised.exception.code, "variable_format_invalid")
        self.assertEqual(raised.exception.parameters["name"], "date")
        self.assertEqual(raised.exception.parameters["format"], "verbose")

    def test_explicit_locale_argument_is_reserved_for_a_later_stage(self):
        with self.assertRaises(VariableResolutionError) as raised:
            self.render("{{date:long:en}}")

        self.assertEqual(
            raised.exception.code,
            "variable_argument_count_invalid",
        )

    def test_clipboard_inserts_current_unicode_text_verbatim(self):
        self.assertEqual(
            self.render(
                "Before {{clipboard}} after",
                get_clipboard_text=lambda: "Copied {{date}} text",
            ),
            "Before Copied {{date}} text after",
        )

    def test_empty_clipboard_text_is_a_valid_value(self):
        self.assertEqual(
            self.render("{{clipboard}}", get_clipboard_text=lambda: ""),
            "",
        )

    def test_non_text_clipboard_resolves_to_empty_string(self):
        self.assertEqual(
            self.render(
                "before{{clipboard}}after",
                get_clipboard_text=lambda: None,
            ),
            "beforeafter",
        )

    def test_app_inserts_target_executable_filename(self):
        self.assertEqual(
            self.render("{{app}}", get_application_name=lambda: "notepad.exe"),
            "notepad.exe",
        )

    def test_missing_target_application_is_reported(self):
        with self.assertRaises(VariableResolutionError) as raised:
            self.render("{{app}}", get_application_name=lambda: None)

        self.assertEqual(
            raised.exception.code,
            "variable_target_application_unavailable",
        )

    def test_context_variables_reject_arguments_during_validation(self):
        for template in ("{{clipboard:text}}", "{{app:name}}"):
            with self.subTest(template=template):
                with self.assertRaises(VariableResolutionError) as raised:
                    self.engine.validate(template)
                self.assertEqual(
                    raised.exception.code,
                    "variable_arguments_unsupported",
                )

    def test_validation_does_not_require_runtime_context(self):
        self.engine.validate(
            "{{clipboard}} {{app}} {{date:long}} {{input:Kundennummer}}"
        )

    def test_input_inserts_the_entered_text_verbatim(self):
        self.assertEqual(
            self.render(
                "Customer: {{input:Kundennummer}}",
                request_input=lambda label: "42 {{date}}",
            ),
            "Customer: 42 {{date}}",
        )

    def test_input_passes_its_label_to_the_runtime_context(self):
        labels = []

        self.render(
            "{{input:Kundennummer}}",
            request_input=lambda label: labels.append(label) or "42",
        )

        self.assertEqual(labels, ["Kundennummer"])

    def test_input_requires_exactly_one_non_empty_label(self):
        for template in ("{{input}}", "{{input: }}", "{{input:label:extra}}"):
            with self.subTest(template=template):
                with self.assertRaises(VariableResolutionError) as raised:
                    self.engine.validate(template)
                self.assertEqual(
                    raised.exception.code,
                    "variable_input_label_required",
                )

    def test_cancelled_input_cancels_the_rendering(self):
        with self.assertRaises(VariableRenderingCancelled):
            self.render(
                "{{input:Kundennummer}}",
                request_input=lambda label: None,
            )

    def test_cursor_is_removed_and_records_offset_from_end(self):
        rendered = self.engine.render(
            "Greeting {{cursor}}🙂\nEnd",
            ResolutionContext(self.timestamp, "de"),
        )

        self.assertEqual(rendered.text, "Greeting 🙂\nEnd")
        self.assertEqual(rendered.cursor_offset_from_end, 5)

    def test_cursor_at_end_records_zero_offset(self):
        rendered = self.engine.render(
            "Greeting{{cursor}}",
            ResolutionContext(self.timestamp, "de"),
        )

        self.assertEqual(rendered, RenderedSnippet("Greeting", 0))

    def test_cursor_rejects_arguments(self):
        with self.assertRaises(VariableResolutionError) as raised:
            self.engine.validate("{{cursor:left}}")

        self.assertEqual(raised.exception.code, "variable_arguments_unsupported")

    def test_cursor_may_occur_only_once_and_is_checked_when_saving(self):
        with self.assertRaises(VariableResolutionError) as raised:
            self.engine.validate("{{cursor}}middle{{cursor}}")

        self.assertEqual(raised.exception.code, "variable_occurrence_limit")
        self.assertEqual(raised.exception.parameters["name"], "cursor")


if __name__ == "__main__":
    unittest.main()
