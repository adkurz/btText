import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from core.variables import (
    RenderedSnippet,
    ResolutionContext,
    UnknownVariableError,
    VariableDefinition,
    VariableEngine,
    VariableRegistry,
    VariableResolutionError,
    VariableSyntaxError,
)


class VariableEngineTestCase(unittest.TestCase):
    def setUp(self):
        self.context = ResolutionContext(
            timestamp=datetime(2026, 8, 6, 14, 35, tzinfo=timezone.utc),
            locale="de",
        )
        self.registry = VariableRegistry(
            [
                VariableDefinition(
                    "value",
                    lambda context, arguments: "resolved",
                ),
                VariableDefinition(
                    "parameters",
                    lambda context, arguments: "|".join(arguments),
                ),
            ]
        )
        self.engine = VariableEngine(self.registry)

    def test_plain_text_is_preserved_exactly(self):
        template = "Grüße {name}\r\nSecond line"

        result = self.engine.render(template, self.context)

        self.assertEqual(result, RenderedSnippet(template))
        self.assertIsNone(result.cursor_offset_from_end)

    def test_variables_are_resolved_at_any_position(self):
        result = self.engine.render(
            "{{value}}/{{value}}/{{parameters:short:de}}",
            self.context,
        )

        self.assertEqual(result.text, "resolved/resolved/short|de")

    def test_resolver_receives_the_shared_context(self):
        received_contexts = []
        registry = VariableRegistry(
            [
                VariableDefinition(
                    "capture",
                    lambda context, arguments: (
                        received_contexts.append(context) or "captured"
                    ),
                )
            ]
        )

        VariableEngine(registry).render(
            "{{capture}} {{capture}}",
            self.context,
        )

        self.assertEqual(received_contexts, [self.context, self.context])

    def test_resolved_text_is_not_interpreted_recursively(self):
        registry = VariableRegistry(
            [VariableDefinition("outer", lambda context, arguments: "{{value}}")]
        )

        result = VariableEngine(registry).render("{{outer}}", self.context)

        self.assertEqual(result.text, "{{value}}")

    def test_delimiters_can_be_escaped(self):
        result = self.engine.render(
            "{{{{value}}}} and }}}}",
            self.context,
        )

        self.assertEqual(result.text, "{{value}} and }}")

    def test_unknown_variable_has_a_stable_error(self):
        with self.assertRaises(UnknownVariableError) as raised:
            self.engine.render("Before {{missing}}", self.context)

        self.assertEqual(raised.exception.code, "variable_unknown")
        self.assertEqual(raised.exception.parameters["name"], "missing")
        self.assertEqual(raised.exception.parameters["position"], 7)

    def test_malformed_templates_are_rejected(self):
        invalid_templates = (
            "{{value",
            "value}}",
            "{{}}",
            "{{Value}}",
            "{{value:}}",
            "{{value::long}}",
            "{{value {{nested}}}}",
        )

        for template in invalid_templates:
            with self.subTest(template=template):
                with self.assertRaises(VariableSyntaxError):
                    self.engine.render(template, self.context)

    def test_resolver_failure_is_wrapped_without_template_content(self):
        def fail(context, arguments):
            raise RuntimeError("provider failed")

        engine = VariableEngine(
            VariableRegistry([VariableDefinition("failure", fail)])
        )

        with self.assertRaises(VariableResolutionError) as raised:
            engine.render("Private text {{failure}}", self.context)

        self.assertEqual(raised.exception.code, "variable_resolution_failed")
        self.assertEqual(raised.exception.parameters["name"], "failure")
        self.assertNotIn("Private text", str(raised.exception))

    def test_non_text_resolver_result_is_rejected(self):
        engine = VariableEngine(
            VariableRegistry(
                [
                    VariableDefinition(
                        "number",
                        lambda context, arguments: 42,  # type: ignore
                    )
                ]
            )
        )

        with self.assertRaises(VariableResolutionError):
            engine.render("{{number}}", self.context)

    def test_validation_checks_arguments_without_calling_resolver(self):
        resolver = Mock(return_value="resolved")
        validator = Mock()
        engine = VariableEngine(
            VariableRegistry(
                [VariableDefinition("value", resolver, validator)]
            )
        )

        engine.validate("{{value:format}}")

        validator.assert_called_once_with(("format",))
        resolver.assert_not_called()


class VariableRegistryTestCase(unittest.TestCase):
    def test_new_definition_can_be_registered_independently(self):
        registry = VariableRegistry()
        definition = VariableDefinition(
            "date",
            lambda context, arguments: context.timestamp.date().isoformat(),
        )

        registry.register(definition)

        self.assertIs(registry.get("date"), definition)

    def test_duplicate_name_is_rejected(self):
        definition = VariableDefinition("date", lambda context, arguments: "")
        registry = VariableRegistry([definition])

        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(definition)

    def test_names_are_canonical_and_language_independent(self):
        invalid_names = ("Date", "1date", "date format", "date.locale")

        for name in invalid_names:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    VariableRegistry(
                        [VariableDefinition(name, lambda context, arguments: "")]
                    )


if __name__ == "__main__":
    unittest.main()
