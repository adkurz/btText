import unittest
from datetime import datetime, timezone

from core.builtin_variables import create_builtin_variable_engine
from core.variables import ResolutionContext, VariableResolutionError


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

    def render(self, template, locale="de"):
        return self.engine.render(
            template,
            ResolutionContext(self.timestamp, locale),
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


if __name__ == "__main__":
    unittest.main()
