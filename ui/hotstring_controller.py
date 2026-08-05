"""Coordinate global hotstring monitoring and expansion."""

from collections.abc import Callable

import wx

from core import datamodel
from core.app_settings import AppSettings
from core.events import EventEmitter
from core.variables import RenderedSnippet, VariableError
from i18n import _
from platform_support import clipboard, hotstring_expansion, hotstrings, windows
from platform_support.clipboard_paste import PendingPaste
from ui.variable_resolver import show_variable_error


class HotstringController:
    """Own the keyboard hook and expand recognized snippet hotstrings."""

    def __init__(
        self,
        parent: wx.Window,
        ee: EventEmitter,
        model: datamodel.DataModel,
        get_settings: Callable[[], AppSettings],
        schedule_clipboard_restore: Callable[[PendingPaste], None],
        notify_expansion: Callable[[datamodel.Snippet], None],
        render_snippet: Callable[[str], RenderedSnippet],
    ):
        """Create the hook and subscribe to snippet mutations."""
        self._parent = parent
        self._model = model
        self._get_settings = get_settings
        self._schedule_clipboard_restore = schedule_clipboard_restore
        self._notify_expansion = notify_expansion
        self._render_snippet = render_snippet
        self._hook = hotstrings.KeyboardHook(
            self._queue_expansion,
            lambda: windows.is_external_window(windows.get_foreground_window()),
        )
        ee.on("snippet.added", self.refresh)
        ee.on("snippet.edited", self.refresh)
        ee.on("snippet.deleted", self.refresh)

    def start(self) -> bool:
        """Start monitoring and report whether the hook was installed."""
        try:
            self._hook.start()
        except OSError as error:
            wx.MessageBox(
                str(error),
                # Translators: Title for a failure to monitor or expand a
                # globally typed snippet hotstring.
                _("Hotstring error"),
                wx.OK | wx.ICON_ERROR,
                self._parent,
            )
            return False
        return True

    def stop(self) -> None:
        """Stop monitoring; repeated calls are harmless."""
        self._hook.stop()

    def refresh(self, *_arguments) -> None:
        """Reload active hotstrings after any snippet mutation."""
        snippets = self._model.get_hotstring_snippets()
        self._hook.update(
            {snippet.hotstring: snippet for snippet in snippets if snippet.hotstring}
        )

    def _queue_expansion(
        self,
        snippet: datamodel.Snippet,
        boundary_key: int,
    ) -> bool:
        """Queue expansion only when the foreground window is external."""
        target_window = windows.get_foreground_window()
        if not windows.is_external_window(target_window):
            return False
        wx.CallAfter(
            self._expand,
            target_window,
            snippet,
            boundary_key,
        )
        return True

    def _expand(
        self,
        target_window: int,
        snippet: datamodel.Snippet,
        boundary_key: int,
    ) -> None:
        """Replace a recognized hotstring through the clipboard paste path."""
        settings = self._get_settings()
        try:
            rendered = self._render_snippet(snippet.content)
        except VariableError as error:
            show_variable_error(self._parent, error)
            return
        try:
            pending = hotstring_expansion.expand_hotstring(
                target_window,
                rendered.text,
                len(snippet.hotstring or ""),
                boundary_key if settings.preserve_hotstring_boundary else None,
            )
        except clipboard.ClipboardError as error:
            wx.MessageBox(
                str(error),
                # Translators: Title for a failure to monitor or expand a
                # globally typed snippet hotstring.
                _("Hotstring error"),
                wx.OK | wx.ICON_ERROR,
                self._parent,
            )
            return
        self._schedule_clipboard_restore(pending)
        if settings.notify_hotstring_expansion:
            self._notify_expansion(snippet)
