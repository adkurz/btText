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


_LOCALIZED_FORMATS = frozenset(("short", "medium", "long", "full"))
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


def create_builtin_variable_engine() -> VariableEngine:
    """Create an engine containing every built-in snippet variable."""
    return VariableEngine(
        VariableRegistry(
            (
                VariableDefinition("date", _resolve_date),
                VariableDefinition("time", _resolve_time),
                VariableDefinition("datetime", _resolve_datetime),
            )
        )
    )
