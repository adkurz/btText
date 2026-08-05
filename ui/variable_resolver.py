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

    def render(self, template: str) -> RenderedSnippet:
        """Capture one timestamp and locale, then render a snippet."""
        context = ResolutionContext(
            timestamp=self._get_timestamp(),
            locale=self._get_locale(),
        )
        return self._engine.render(template, context)

    @staticmethod
    def _current_timestamp() -> datetime:
        """Return a timezone-aware local timestamp."""
        return datetime.now().astimezone()


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
