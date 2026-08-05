"""Parse and resolve variables embedded in snippet text."""

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


@dataclass(frozen=True)
class ResolutionContext:
    """Values captured once and shared by every variable in one rendering."""

    timestamp: datetime
    locale: str
    get_clipboard_text: Callable[[], str | None] | None = None
    get_application_name: Callable[[], str | None] | None = None


VariableResolver = Callable[[ResolutionContext, tuple[str, ...]], str]
VariableArgumentValidator = Callable[[tuple[str, ...]], None]


@dataclass(frozen=True)
class VariableDefinition:
    """Describe one named variable and the function that resolves it."""

    name: str
    resolver: VariableResolver
    validate_arguments: VariableArgumentValidator | None = None


@dataclass(frozen=True)
class RenderedSnippet:
    """A rendered snippet plus metadata for future insertion directives."""

    text: str
    cursor_offset_from_end: int | None = None


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
        self._definitions[definition.name] = definition

    def get(self, name: str) -> VariableDefinition | None:
        """Return the registered definition for ``name``, if present."""
        return self._definitions.get(name)


class VariableEngine:
    """Render snippet templates through an explicit variable registry."""

    def __init__(self, registry: VariableRegistry) -> None:
        self._registry = registry

    def render(
        self,
        template: str,
        context: ResolutionContext,
    ) -> RenderedSnippet:
        """Resolve variables once without recursively interpreting results."""
        parts: list[str] = []
        for part in self._parse(template):
            if isinstance(part, str):
                parts.append(part)
                continue
            definition = self._get_validated_definition(part)
            try:
                value = definition.resolver(context, part.arguments)
                if not isinstance(value, str):
                    raise TypeError("The variable resolver did not return text.")
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
        return RenderedSnippet(text="".join(parts))

    def validate(self, template: str) -> None:
        """Validate syntax, names, and arguments without resolving values."""
        for part in self._parse(template):
            if isinstance(part, _VariableToken):
                self._get_validated_definition(part)

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
