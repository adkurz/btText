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
    VariableRenderingCancelled,
)
from i18n import _
from platform_support import clipboard, windows
from ui.variable_dialog import InteractiveVariablesDialog


class SnippetVariableResolver:
    """Bridge the generic engine to wx and Windows insertion-time services.

    The plan-first flow is important for extensions: interactive definitions
    declare labels in the core catalog, this class opens one combined dialog,
    and only then does the engine resolve the template.  A new variable should
    need changes here only if it requires a genuinely new runtime service, in
    which case expose that service through ``ResolutionContext`` as a callable
    so validation stays side-effect free and tests can inject a replacement.
    """

    def __init__(
        self,
        engine: VariableEngine,
        parent: wx.Window | None = None,
        get_timestamp: Callable[[], datetime] | None = None,
        get_locale: Callable[[], str] | None = None,
        request_inputs: (
            Callable[[tuple[str, ...]], dict[str, str] | None] | None
        ) = None,
    ) -> None:
        self._engine = engine
        self._parent = parent
        self._get_timestamp = get_timestamp or self._current_timestamp
        self._get_locale = get_locale or i18n.get_formatting_locale
        self._request_inputs = request_inputs or self._show_input_dialog

    def render(
        self,
        template: str,
        target_window: int | None = None,
    ) -> RenderedSnippet:
        """Collect all interactive values, capture context, then render once."""
        plan = self._engine.plan(template)
        answers: dict[str, str] = {}
        if plan.input_labels:
            requested_answers = self._request_inputs(plan.input_labels)
            if requested_answers is None:
                raise VariableRenderingCancelled
            answers = requested_answers
        context = ResolutionContext(
            timestamp=self._get_timestamp(),
            locale=self._get_locale(),
            get_clipboard_text=self._memoize(clipboard.read_text),
            get_application_name=self._memoize(
                lambda: windows.get_window_application_name(target_window)
            ),
            # Interactive resolvers look up answers collected during planning;
            # they never create UI while the engine is resolving the template.
            request_input=lambda label: answers[label],
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

    def _show_input_dialog(
        self,
        labels: tuple[str, ...],
    ) -> dict[str, str] | None:
        """Collect every interactive variable value in one dialog."""
        dialog = InteractiveVariablesDialog(self._parent, labels)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return None
            return dialog.get_values()
        finally:
            dialog.Destroy()


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
