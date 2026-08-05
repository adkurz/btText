"""Build per-insertion context and render snippet variables."""

from collections.abc import Callable
from datetime import datetime

import i18n
import wx

from core.error_messages import format_user_error
from core.variables import (
    RenderedSnippet,
    ResolutionContext,
    VariableEngine,
    VariableError,
)
from i18n import _
from platform_support import clipboard, windows


class SnippetVariableResolver:
    """Resolve snippet text using values captured once per insertion."""

    def __init__(
        self,
        engine: VariableEngine,
        get_timestamp: Callable[[], datetime] | None = None,
        get_locale: Callable[[], str] = i18n.get_active_language,
    ) -> None:
        self._engine = engine
        self._get_timestamp = get_timestamp or self._current_timestamp
        self._get_locale = get_locale

    def render(
        self,
        template: str,
        target_window: int | None = None,
    ) -> RenderedSnippet:
        """Capture one timestamp and locale, then render a snippet."""
        context = ResolutionContext(
            timestamp=self._get_timestamp(),
            locale=self._get_locale(),
            get_clipboard_text=self._memoize(clipboard.read_text),
            get_application_name=self._memoize(
                lambda: windows.get_window_application_name(target_window)
            ),
        )
        return self._engine.render(template, context)

    def validate(self, template: str) -> None:
        """Validate a template without reading runtime context values."""
        self._engine.validate(template)

    @staticmethod
    def _current_timestamp() -> datetime:
        """Return a timezone-aware local timestamp."""
        return datetime.now().astimezone()

    @staticmethod
    def _memoize(get_value: Callable[[], str | None]) -> Callable[[], str | None]:
        """Read one contextual value at most once during a rendering."""
        missing = object()
        value: object = missing

        def get_once() -> str | None:
            nonlocal value
            if value is missing:
                value = get_value()
            return value  # type: ignore[return-value]

        return get_once


def show_variable_error(parent: wx.Window, error: VariableError) -> None:
    """Present a localized variable error at the shared UI boundary."""
    wx.MessageBox(
        format_user_error(error),
        # Translators: Title for a variable error that prevents a snippet from
        # being inserted manually or expanded through a hotstring.
        _("Variable error"),
        wx.OK | wx.ICON_ERROR,
        parent,
    )
