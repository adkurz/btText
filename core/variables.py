"""Parse, validate, plan, and resolve variables embedded in snippet text.

This module contains the generic variable engine.  It deliberately knows
nothing about btText's concrete variables or wx UI.  Most new built-in
variables therefore do *not* require changes here: implement their callbacks
and add a catalog entry in :mod:`core.builtin_variables` instead.

A definition participates in up to three separate phases:

* ``validate_arguments`` checks an expression without reading runtime state.
* ``collect_input_labels`` declares values that the UI must collect first.
* ``resolver`` turns the already validated expression into text at insertion.

Keeping those phases separate lets the editor validate snippets without side
effects and lets the UI ask for all interactive values in a single dialog.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
import re

from core.user_errors import UserFacingError


_VARIABLE_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_-]*\Z")


class VariableError(UserFacingError):
    """Base class for variable errors that may reach a UI boundary."""


class VariableSyntaxError(VariableError):
    """Raised when snippet text contains malformed variable syntax."""


class UnknownVariableError(VariableError):
    """Raised when no registered definition matches a variable name."""


class VariableResolutionError(VariableError):
    """Raised when a registered variable cannot produce a text value."""


class VariableRenderingCancelled(Exception):
    """Raised when a user cancels an interactive variable rendering."""


@dataclass(frozen=True)
class ResolutionContext:
    """Runtime services and snapshot values shared by one rendering.

    New resolvers should obtain time, locale, clipboard, application, and user
    input exclusively through this object.  Do not read those sources directly:
    the UI layer captures or memoizes them so repeated variables in the same
    snippet observe consistent values and remain straightforward to test.
    """

    timestamp: datetime
    locale: str
    get_clipboard_text: Callable[[], str | None] | None = None
    get_application_name: Callable[[], str | None] | None = None
    request_input: Callable[[str], str | None] | None = None


@dataclass(frozen=True)
class ResolvedVariable:
    """Return text plus an insertion instruction from a resolver.

    A normal textual variable may simply return ``str``.  Use this wrapper only
    when the variable also needs engine-level metadata, such as ``{{cursor}}``.
    """

    text: str = ""
    cursor_position: bool = False


# Resolver and extension-hook signatures are aliases so a new definition can
# be type checked without depending on the engine's private token model.
VariableResolver = Callable[
    [ResolutionContext, tuple[str, ...]],
    str | ResolvedVariable,
]
VariableArgumentValidator = Callable[[tuple[str, ...]], None]
VariableInputCollector = Callable[[tuple[str, ...]], tuple[str, ...]]


@dataclass(frozen=True)
class VariableDefinition:
    """Describe the runtime contract of one named variable.

    ``resolver`` is the only mandatory hook.  Add ``validate_arguments`` when
    arguments have a constrained shape; it must not read external state.
    ``collect_input_labels`` is for interactive variables and must return the
    labels needed before rendering.  ``maximum_occurrences`` enforces a limit
    across one template, rather than one call to the resolver.
    """

    name: str
    resolver: VariableResolver
    validate_arguments: VariableArgumentValidator | None = None
    maximum_occurrences: int | None = None
    collect_input_labels: VariableInputCollector | None = None


@dataclass(frozen=True)
class RenderedSnippet:
    """A rendered snippet plus metadata for future insertion directives."""

    text: str
    cursor_offset_from_end: int | None = None


@dataclass(frozen=True)
class ResolutionPlan:
    """Describe user input required before resolving a template.

    Labels are distinct and retain their first-occurrence order so a UI can
    present one predictable combined dialog.  Planning never calls resolvers.
    """

    input_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class _VariableToken:
    name: str
    arguments: tuple[str, ...]
    position: int


class VariableRegistry:
    """Store explicitly registered variable definitions by canonical name."""

    def __init__(
        self,
        definitions: Iterable[VariableDefinition] = (),
    ) -> None:
        self._definitions: dict[str, VariableDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: VariableDefinition) -> None:
        """Register one definition, rejecting invalid or duplicate names."""
        if not _VARIABLE_NAME_PATTERN.fullmatch(definition.name):
            raise ValueError(
                "Variable names must start with a lowercase ASCII letter and "
                "contain only lowercase ASCII letters, digits, '_' or '-'."
            )
        if definition.name in self._definitions:
            raise ValueError(
                f"Variable {definition.name!r} is already registered."
            )
        if not callable(definition.resolver):
            raise TypeError("The variable resolver must be callable.")
        if (
            definition.validate_arguments is not None
            and not callable(definition.validate_arguments)
        ):
            raise TypeError("The variable argument validator must be callable.")
        if (
            definition.maximum_occurrences is not None
            and definition.maximum_occurrences < 1
        ):
            raise ValueError("The variable occurrence limit must be positive.")
        if (
            definition.collect_input_labels is not None
            and not callable(definition.collect_input_labels)
        ):
            raise TypeError("The variable input collector must be callable.")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> VariableDefinition | None:
        """Return the registered definition for ``name``, if present."""
        return self._definitions.get(name)


class VariableEngine:
    """Render snippet templates through an explicit variable registry.

    Resolution is intentionally nonrecursive: text returned by a resolver is
    inserted literally even if it contains ``{{...}}``.  This prevents values
    from accidentally becoming executable template syntax.
    """

    def __init__(self, registry: VariableRegistry) -> None:
        self._registry = registry

    def render(
        self,
        template: str,
        context: ResolutionContext,
    ) -> RenderedSnippet:
        """Resolve variables once without recursively interpreting results."""
        parts: list[str] = []
        cursor_position: int | None = None
        occurrences: dict[str, int] = {}
        for part in self._parse(template):
            if isinstance(part, str):
                parts.append(part)
                continue
            definition = self._get_validated_definition(part)
            self._validate_occurrence(definition, part, occurrences)
            try:
                resolved = definition.resolver(context, part.arguments)
                if isinstance(resolved, ResolvedVariable):
                    value = resolved.text
                    if resolved.cursor_position:
                        cursor_position = sum(len(item) for item in parts) + len(value)
                elif isinstance(resolved, str):
                    value = resolved
                else:
                    raise TypeError("The variable resolver did not return text.")
            except VariableRenderingCancelled:
                raise
            except VariableError:
                raise
            except Exception as error:
                raise VariableResolutionError(
                    "variable_resolution_failed",
                    "Variable {name!r} at position {position} could not be "
                    "resolved: {reason}",
                    name=part.name,
                    position=part.position,
                    reason=error,
                ) from error
            parts.append(value)
        text = "".join(parts)
        return RenderedSnippet(
            text=text,
            cursor_offset_from_end=(
                None if cursor_position is None else len(text) - cursor_position
            ),
        )

    def validate(self, template: str) -> None:
        """Validate syntax, names, and arguments without resolving values."""
        self.plan(template)

    def plan(self, template: str) -> ResolutionPlan:
        """Validate and collect interactive inputs without resolving values."""
        occurrences: dict[str, int] = {}
        input_labels: list[str] = []
        known_labels: set[str] = set()
        for part in self._parse(template):
            if isinstance(part, _VariableToken):
                definition = self._get_validated_definition(part)
                self._validate_occurrence(definition, part, occurrences)
                if definition.collect_input_labels is not None:
                    for label in definition.collect_input_labels(part.arguments):
                        if label not in known_labels:
                            known_labels.add(label)
                            input_labels.append(label)
        return ResolutionPlan(tuple(input_labels))

    @staticmethod
    def _validate_occurrence(
        definition: VariableDefinition,
        token: _VariableToken,
        occurrences: dict[str, int],
    ) -> None:
        """Enforce an optional per-template occurrence limit."""
        count = occurrences.get(token.name, 0) + 1
        occurrences[token.name] = count
        if (
            definition.maximum_occurrences is not None
            and count > definition.maximum_occurrences
        ):
            raise VariableResolutionError(
                "variable_occurrence_limit",
                "Variable {name!r} exceeds its occurrence limit",
                name=token.name,
                maximum=definition.maximum_occurrences,
            )

    def _get_validated_definition(
        self,
        token: _VariableToken,
    ) -> VariableDefinition:
        """Return a known definition after validating its arguments."""
        definition = self._registry.get(token.name)
        if definition is None:
            raise UnknownVariableError(
                "variable_unknown",
                "Unknown variable {name!r} at position {position}",
                name=token.name,
                position=token.position,
            )
        if definition.validate_arguments is not None:
            definition.validate_arguments(token.arguments)
        return definition

    @staticmethod
    def _parse(template: str) -> list[str | _VariableToken]:
        """Split a template into literal text and variable tokens."""
        parts: list[str | _VariableToken] = []
        literal: list[str] = []
        position = 0

        def flush_literal() -> None:
            if literal:
                parts.append("".join(literal))
                literal.clear()

        while position < len(template):
            if template.startswith("{{{{", position):
                literal.append("{{")
                position += 4
                continue
            if template.startswith("}}}}", position):
                literal.append("}}")
                position += 4
                continue
            if template.startswith("{{", position):
                flush_literal()
                token_position = position
                end = template.find("}}", position + 2)
                if end < 0:
                    raise VariableSyntaxError(
                        "variable_syntax_invalid",
                        "Variable starting at position {position} is not closed",
                        position=token_position,
                    )
                expression = template[position + 2 : end]
                parts.append(
                    VariableEngine._parse_expression(expression, token_position)
                )
                position = end + 2
                continue
            if template.startswith("}}", position):
                raise VariableSyntaxError(
                    "variable_syntax_invalid",
                    "Unexpected variable closing delimiter at position {position}",
                    position=position,
                )
            literal.append(template[position])
            position += 1

        flush_literal()
        return parts

    @staticmethod
    def _parse_expression(expression: str, position: int) -> _VariableToken:
        """Validate a variable expression and return its canonical parts."""
        if "{{" in expression or "}}" in expression:
            raise VariableSyntaxError(
                "variable_syntax_invalid",
                "Nested variable syntax at position {position} is not allowed",
                position=position,
            )
        components = expression.split(":")
        name = components[0]
        if not _VARIABLE_NAME_PATTERN.fullmatch(name):
            raise VariableSyntaxError(
                "variable_name_invalid",
                "Invalid variable name at position {position}",
                position=position,
            )
        arguments = tuple(components[1:])
        if any(
            not argument or "{{" in argument or "}}" in argument
            for argument in arguments
        ):
            raise VariableSyntaxError(
                "variable_syntax_invalid",
                "Invalid variable argument at position {position}",
                position=position,
            )
        return _VariableToken(name, arguments, position)
