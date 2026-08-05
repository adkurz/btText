"""Built-in snippet variables with locale-aware date and time formatting."""

from collections.abc import Callable
from datetime import date, datetime, time

from babel.dates import format_date, format_datetime, format_time

from core.variables import (
    ResolutionContext,
    VariableDefinition,
    VariableEngine,
    VariableRegistry,
    VariableResolutionError,
)


TEMPORAL_VARIABLE_NAMES = ("date", "time", "datetime")
CONTEXT_VARIABLE_NAMES = ("clipboard", "app")
BUILTIN_VARIABLE_NAMES = TEMPORAL_VARIABLE_NAMES + CONTEXT_VARIABLE_NAMES
BUILTIN_VARIABLE_FORMATS = ("short", "medium", "long", "full", "iso")
_LOCALIZED_FORMATS = frozenset(BUILTIN_VARIABLE_FORMATS[:-1])
_DEFAULT_FORMAT = "short"


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


def create_builtin_variable_engine() -> VariableEngine:
    """Create an engine containing every built-in snippet variable."""
    resolvers = {
        "date": _resolve_date,
        "time": _resolve_time,
        "datetime": _resolve_datetime,
        "clipboard": _resolve_clipboard,
        "app": _resolve_app,
    }
    argument_validators = {
        "date": lambda arguments: _requested_format("date", arguments),
        "time": lambda arguments: _requested_format("time", arguments),
        "datetime": lambda arguments: _requested_format("datetime", arguments),
        "clipboard": lambda arguments: _reject_arguments("clipboard", arguments),
        "app": lambda arguments: _reject_arguments("app", arguments),
    }
    return VariableEngine(
        VariableRegistry(
            tuple(
                VariableDefinition(
                    name,
                    resolvers[name],
                    argument_validators[name],
                )
                for name in BUILTIN_VARIABLE_NAMES
            )
        )
    )
