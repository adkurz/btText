"""Built-in snippet variables with locale-aware date and time formatting."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum, auto

from babel.dates import format_date, format_datetime, format_time

from core.variables import (
    ResolutionContext,
    ResolvedVariable,
    VariableDefinition,
    VariableEngine,
    VariableRegistry,
    VariableRenderingCancelled,
    VariableResolutionError,
)


BUILTIN_VARIABLE_FORMATS = ("short", "medium", "long", "full", "iso")
_LOCALIZED_FORMATS = frozenset(BUILTIN_VARIABLE_FORMATS[:-1])
_DEFAULT_FORMAT = "short"


class VariableEditorKind(Enum):
    """Describe how the editor configures a built-in variable."""

    PLAIN = auto()
    TEMPORAL_FORMAT = auto()
    INPUT_LABEL = auto()


class VariableDescription(Enum):
    """Identify a localizable built-in variable description."""

    DATE = auto()
    TIME = auto()
    DATETIME = auto()
    CLIPBOARD = auto()
    APPLICATION = auto()
    INPUT = auto()
    CURSOR = auto()


@dataclass(frozen=True)
class BuiltinVariable:
    """Declare runtime and editor metadata for one built-in variable."""

    definition: VariableDefinition
    description: VariableDescription
    editor_kind: VariableEditorKind = VariableEditorKind.PLAIN
    editor_options: tuple[str, ...] = ()
    editor_placeholder: str | None = None

    def __post_init__(self) -> None:
        """Reject inconsistent editor metadata when defining the catalog."""
        if self.editor_kind is VariableEditorKind.PLAIN:
            if self.editor_options or self.editor_placeholder is not None:
                raise ValueError("A plain variable cannot define editor settings.")
            return
        if self.editor_kind is VariableEditorKind.TEMPORAL_FORMAT:
            if not self.editor_options or self.editor_placeholder is not None:
                raise ValueError(
                    "A temporal variable requires format options only."
                )
            return
        if (
            not self.editor_placeholder
            or self.editor_options
        ):
            raise ValueError(
                "An input variable requires one editor placeholder only."
            )


def _requested_format(
    variable_name: str,
    arguments: tuple[str, ...],
) -> str:
    """Return one supported format name for a temporal variable."""
    if len(arguments) > 1:
        raise VariableResolutionError(
            "variable_argument_count_invalid",
            "Variable {name!r} accepts at most one format argument",
            name=variable_name,
        )
    requested_format = arguments[0] if arguments else _DEFAULT_FORMAT
    if requested_format not in _LOCALIZED_FORMATS and requested_format != "iso":
        raise VariableResolutionError(
            "variable_format_invalid",
            "Format {format!r} is not supported for variable {name!r}",
            name=variable_name,
            format=requested_format,
        )
    return requested_format


def _reject_arguments(
    variable_name: str,
    arguments: tuple[str, ...],
) -> None:
    """Reject arguments for a context variable that accepts none."""
    if arguments:
        raise VariableResolutionError(
            "variable_arguments_unsupported",
            "Variable {name!r} does not accept arguments",
            name=variable_name,
        )


def _resolve_temporal(
    variable_name: str,
    value: date | time | datetime,
    arguments: tuple[str, ...],
    locale: str,
    localized_formatter: Callable[..., str],
) -> str:
    """Format one temporal value using ISO or a named CLDR format."""
    requested_format = _requested_format(variable_name, arguments)
    if requested_format == "iso":
        if isinstance(value, datetime):
            return value.isoformat(timespec="seconds")
        if isinstance(value, time):
            return value.isoformat(timespec="seconds")
        return value.isoformat()
    return localized_formatter(
        value,
        format=requested_format,
        locale=locale,
    )


def _resolve_date(
    context: ResolutionContext,
    arguments: tuple[str, ...],
) -> str:
    return _resolve_temporal(
        "date",
        context.timestamp.date(),
        arguments,
        context.locale,
        format_date,
    )


def _resolve_time(
    context: ResolutionContext,
    arguments: tuple[str, ...],
) -> str:
    return _resolve_temporal(
        "time",
        context.timestamp.timetz(),
        arguments,
        context.locale,
        format_time,
    )


def _resolve_datetime(
    context: ResolutionContext,
    arguments: tuple[str, ...],
) -> str:
    return _resolve_temporal(
        "datetime",
        context.timestamp,
        arguments,
        context.locale,
        format_datetime,
    )


def _resolve_clipboard(
    context: ResolutionContext,
    arguments: tuple[str, ...],
) -> str:
    _reject_arguments("clipboard", arguments)
    if context.get_clipboard_text is None:
        raise VariableResolutionError(
            "variable_context_unavailable",
            "No clipboard context is available for the variable",
            name="clipboard",
        )
    text = context.get_clipboard_text()
    return "" if text is None else text


def _resolve_app(
    context: ResolutionContext,
    arguments: tuple[str, ...],
) -> str:
    _reject_arguments("app", arguments)
    if context.get_application_name is None:
        raise VariableResolutionError(
            "variable_context_unavailable",
            "No target-application context is available for the variable",
            name="app",
        )
    application_name = context.get_application_name()
    if application_name is None:
        raise VariableResolutionError(
            "variable_target_application_unavailable",
            "The target application could not be identified",
            name="app",
        )
    return application_name


def _input_label(arguments: tuple[str, ...]) -> str:
    """Return the required non-empty label for an interactive input."""
    if len(arguments) != 1 or not arguments[0].strip():
        raise VariableResolutionError(
            "variable_input_label_required",
            "Variable 'input' requires exactly one non-empty label",
            name="input",
        )
    return arguments[0]


def _resolve_input(
    context: ResolutionContext,
    arguments: tuple[str, ...],
) -> str:
    label = _input_label(arguments)
    if context.request_input is None:
        raise VariableResolutionError(
            "variable_context_unavailable",
            "No interactive input context is available for the variable",
            name="input",
        )
    value = context.request_input(label)
    if value is None:
        raise VariableRenderingCancelled
    return value


def _resolve_cursor(
    context: ResolutionContext,
    arguments: tuple[str, ...],
) -> ResolvedVariable:
    _reject_arguments("cursor", arguments)
    return ResolvedVariable(cursor_position=True)


def _validate_temporal(
    variable_name: str,
) -> Callable[[tuple[str, ...]], None]:
    """Build an argument validator for one temporal variable."""

    def validate(arguments: tuple[str, ...]) -> None:
        _requested_format(variable_name, arguments)

    return validate


def _validate_no_arguments(
    variable_name: str,
) -> Callable[[tuple[str, ...]], None]:
    """Build an argument validator for one parameterless variable."""

    def validate(arguments: tuple[str, ...]) -> None:
        _reject_arguments(variable_name, arguments)

    return validate


BUILTIN_VARIABLE_CATALOG = (
    BuiltinVariable(
        VariableDefinition("date", _resolve_date, _validate_temporal("date")),
        VariableDescription.DATE,
        VariableEditorKind.TEMPORAL_FORMAT,
        BUILTIN_VARIABLE_FORMATS,
    ),
    BuiltinVariable(
        VariableDefinition("time", _resolve_time, _validate_temporal("time")),
        VariableDescription.TIME,
        VariableEditorKind.TEMPORAL_FORMAT,
        BUILTIN_VARIABLE_FORMATS,
    ),
    BuiltinVariable(
        VariableDefinition(
            "datetime",
            _resolve_datetime,
            _validate_temporal("datetime"),
        ),
        VariableDescription.DATETIME,
        VariableEditorKind.TEMPORAL_FORMAT,
        BUILTIN_VARIABLE_FORMATS,
    ),
    BuiltinVariable(
        VariableDefinition(
            "clipboard",
            _resolve_clipboard,
            _validate_no_arguments("clipboard"),
        ),
        VariableDescription.CLIPBOARD,
    ),
    BuiltinVariable(
        VariableDefinition("app", _resolve_app, _validate_no_arguments("app")),
        VariableDescription.APPLICATION,
    ),
    BuiltinVariable(
        VariableDefinition("input", _resolve_input, _input_label),
        VariableDescription.INPUT,
        VariableEditorKind.INPUT_LABEL,
        editor_placeholder="Prompt",
    ),
    BuiltinVariable(
        VariableDefinition(
            "cursor",
            _resolve_cursor,
            _validate_no_arguments("cursor"),
            maximum_occurrences=1,
        ),
        VariableDescription.CURSOR,
    ),
)

def create_builtin_variable_engine() -> VariableEngine:
    """Create an engine containing every built-in snippet variable."""
    return VariableEngine(
        VariableRegistry(
            variable.definition for variable in BUILTIN_VARIABLE_CATALOG
        )
    )
