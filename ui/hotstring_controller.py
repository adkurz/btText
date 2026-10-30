"""Coordinate global hotstring monitoring and expansion."""

from collections.abc import Callable
from functools import partial
import threading

import wx

from core import datamodel
from core.app_settings import AppSettings
from core.error_messages import format_user_error
from core.events import EventEmitter
from core.hotstrings import HotstringExpansionCancelled, HotstringExpansionError
from core.rich_text import render_clipboard_content
from core.variables import (
    VariableError,
    VariableRenderingCancelled,
)
from i18n import _
from platform_support import (
    clipboard,
    hotstring_expansion,
    hotstrings,
    keyboard_input,
    sounds,
    windows,
)
from platform_support.clipboard_paste import (
    ClipboardPasteSession,
    ClipboardRestoreError,
    PendingPaste,
)
from ui.variable_resolver import SnippetRenderer, show_variable_error


HOTSTRING_SOUND_FILENAME = "hotstring.wav"


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
        render_snippet: SnippetRenderer,
        *,
        clipboard_session: ClipboardPasteSession | None = None,
    ):
        """Create the hook and subscribe to mutations affecting hotstrings."""
        self._parent = parent
        self._model = model
        self._get_settings = get_settings
        self._schedule_clipboard_restore = schedule_clipboard_restore
        self._notify_expansion = notify_expansion
        self._render_snippet = render_snippet
        self._queue_lock = threading.Lock()
        self._clipboard_session = (
            clipboard_session
            if clipboard_session is not None
            else ClipboardPasteSession()
        )
        self._hook = hotstrings.KeyboardHook(
            self._queue_expansion,
            lambda: windows.is_external_window(windows.get_foreground_window()),
        )
        ee.on("snippet.added", self.refresh)
        ee.on("snippet.edited", self.refresh)
        ee.on("snippets.added", self.refresh)
        ee.on("snippets.edited", self.refresh)
        ee.on("snippets.deleted", self.refresh)
        # Category deletion cascades to snippets without emitting snippet events.
        ee.on("category.deleted", self.refresh)

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
        """Reload active hotstrings after snippet changes or category deletion."""
        snippets = self._model.get_hotstring_snippets()
        self._hook.update(
            {snippet.hotstring: snippet for snippet in snippets if snippet.hotstring}
        )

    def _queue_expansion(
        self,
        snippet: datamodel.Snippet,
        boundary_key: keyboard_input.BoundaryInput,
        checkpoint: hotstrings.InputCheckpoint,
    ) -> bool:
        """Queue expansion only when the foreground window is external."""
        if checkpoint.cancelled.is_set():
            return False
        target_window = checkpoint.context[0]
        if not windows.is_external_window(target_window):
            return False
        target_identity = windows.get_window_identity(target_window)
        if target_identity is None:
            return False
        # A modal variable prompt can pump CallAfter callbacks. Keep later
        # matches native instead of nesting expansion dialogs or deleting text.
        if not self._queue_lock.acquire(blocking=False):
            return False
        try:
            wx.CallAfter(
                self._run_queued_expansion,
                target_identity,
                snippet,
                boundary_key,
                checkpoint,
            )
        except Exception:
            self._queue_lock.release()
            raise
        return True

    def _run_queued_expansion(
        self,
        target: windows.WindowIdentity,
        snippet: datamodel.Snippet,
        boundary_key: keyboard_input.BoundaryInput,
        checkpoint: hotstrings.InputCheckpoint,
    ) -> None:
        """Release the queue reservation even after rendering or native errors."""
        try:
            self._expand(target, snippet, boundary_key, checkpoint)
        finally:
            self._queue_lock.release()

    def _expand(
        self,
        target: windows.WindowIdentity,
        snippet: datamodel.Snippet,
        boundary_key: keyboard_input.BoundaryInput,
        checkpoint: hotstrings.InputCheckpoint,
    ) -> None:
        """Replace a recognized hotstring through the clipboard paste path."""
        with self._hook.expansion(checkpoint):
            self._expand_in_session(target, snippet, boundary_key, checkpoint)

    def _expand_in_session(
        self,
        target: windows.WindowIdentity,
        snippet: datamodel.Snippet,
        boundary_key: keyboard_input.BoundaryInput,
        checkpoint: hotstrings.InputCheckpoint,
    ) -> None:
        """Keep prompt ownership through rendering, activation and insertion."""
        if not self._hook.is_current(checkpoint):
            return
        settings = self._get_settings()
        if not settings.hotstrings_enabled:
            return
        is_current = partial(
            self._hook.is_current, checkpoint, allow_own_foreground=True,
        )
        is_target_current = partial(self._hook.is_current, checkpoint)
        try:
            rendered = self._render_snippet(
                snippet.content,
                target.handle,
                snippet.markdown_enabled,
                on_input_requested=partial(self._hook.begin_input, checkpoint),
            )
        except VariableRenderingCancelled:
            self._replay_suppressed_boundary(
                target, boundary_key, checkpoint, is_current, is_target_current,
            )
            return
        except VariableError as error:
            self._replay_suppressed_boundary(
                target, boundary_key, checkpoint, is_current, is_target_current,
            )
            show_variable_error(self._parent, error)
            return
        pending = None
        content = render_clipboard_content(rendered, snippet.markdown_enabled)
        try:
            pending = hotstring_expansion.expand_hotstring(
                target,
                content,
                len(snippet.hotstring or ""),
                boundary_key if settings.preserve_hotstring_boundary else None,
                session=self._clipboard_session,
                is_current=is_current,
                is_target_current=is_target_current,
                target_focus=(
                    checkpoint.context[1] if checkpoint.interactive.is_set() else None
                ),
            )
            if content.cursor_offset_from_end is not None and is_target_current():
                boundary_offset = int(
                    settings.preserve_hotstring_boundary
                    and boundary_key is not None
                )
                keyboard_input.move_cursor_left(
                    content.cursor_offset_from_end + boundary_offset
                )
        except HotstringExpansionCancelled:
            return
        except (clipboard.ClipboardError, HotstringExpansionError) as error:
            if pending is None and isinstance(error, ClipboardRestoreError):
                pending = error.pending_paste
            if pending is not None:
                self._schedule_clipboard_restore(pending)
            self._show_hotstring_error(error)
            return
        self._schedule_clipboard_restore(pending)
        if settings.play_hotstring_sound:
            sounds.play_sound(HOTSTRING_SOUND_FILENAME)
        if settings.notify_hotstring_expansion:
            self._notify_expansion(snippet)

    def _replay_suppressed_boundary(
        self,
        target: windows.WindowIdentity,
        boundary_key: keyboard_input.BoundaryInput,
        checkpoint: hotstrings.InputCheckpoint,
        is_current: Callable[[], bool],
        is_target_current: Callable[[], bool],
    ) -> None:
        """Restore a boundary consumed before variable rendering completed."""
        try:
            hotstring_expansion.replay_suppressed_boundary(
                target,
                boundary_key,
                is_current=is_current,
                is_target_current=is_target_current,
                target_focus=(
                    checkpoint.context[1] if checkpoint.interactive.is_set() else None
                ),
            )
        except HotstringExpansionCancelled:
            return
        except (clipboard.ClipboardError, HotstringExpansionError) as error:
            self._show_hotstring_error(error)

    def _show_hotstring_error(self, error: Exception) -> None:
        """Present a localized hotstring operation failure."""
        wx.MessageBox(
            format_user_error(error),
            # Translators: Title for a failure to monitor or expand a
            # globally typed snippet hotstring.
            _("Hotstring error"),
            wx.OK | wx.ICON_ERROR,
            self._parent,
        )
