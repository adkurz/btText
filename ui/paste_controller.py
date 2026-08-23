"""Coordinate inserting snippets into an external Windows application."""

from collections.abc import Callable

import wx

from core import datamodel
from core.error_messages import format_user_error
from core.variables import (
    RenderedSnippet,
    VariableError,
    VariableRenderingCancelled,
)
from i18n import _
from platform_support import clipboard_paste, keyboard_input, windows
from ui.variable_resolver import show_variable_error

CLIPBOARD_RESTORE_DELAY_MS = 500
PASTE_AFTER_HIDE_DELAY_MS = 50
CLIPBOARD_RESTORE_ATTEMPTS = 3
CLIPBOARD_RESTORE_RETRY_DELAY_MS = 100


class PasteController:
    """Manage the external paste target and delayed clipboard restoration."""

    def __init__(
        self,
        parent: wx.Window,
        model: datamodel.DataModel,
        before_paste: Callable[[], None],
        reveal_after_error: Callable[[str, str], None],
        render_snippet: Callable[[str, int | None], RenderedSnippet],
    ):
        """Initialize paste coordination with explicit frame callbacks."""
        self._parent = parent
        self._model = model
        self._before_paste = before_paste
        self._reveal_after_error = reveal_after_error
        self._render_snippet = render_snippet
        self._target_window: windows.WindowIdentity | None = None
        self.remember_foreground_window()

    def remember_foreground_window(self) -> None:
        """Remember a valid external foreground window as the paste target."""
        foreground_window = windows.get_foreground_window()
        if windows.is_external_window(foreground_window):
            self._target_window = windows.get_window_identity(foreground_window)

    @property
    def target_window(self) -> int | None:
        """Return the currently remembered external paste target."""
        return self._target_window.handle if self._target_window is not None else None

    def insert_snippet(self, snippet_id: int) -> None:
        """Hide the frame and schedule insertion into the previous window."""
        if self._target_window is None:
            wx.MessageBox(
                # Translators: Error when no previously active external window is
                # available as the destination for inserting a snippet.
                _("There is no previous window to insert the snippet into."),
                # Translators: Title of an error inserting a snippet externally.
                _("Paste error"),
                wx.OK | wx.ICON_ERROR,
                self._parent,
            )
            return
        try:
            snippet = self._model.get_snippet(snippet_id)
        except datamodel.DataModelError as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Generic title for a failed snippet operation.
                _("Error"),
                wx.OK | wx.ICON_ERROR,
                self._parent,
            )
            return

        try:
            rendered = self._render_snippet(
                snippet.content,
                self._target_window.handle,
            )
        except VariableRenderingCancelled:
            return
        except VariableError as error:
            show_variable_error(self._parent, error)
            return

        self._before_paste()
        target = self._target_window
        wx.CallLater(
            PASTE_AFTER_HIDE_DELAY_MS,
            self._paste_after_hide,
            target,
            rendered.text,
            rendered.cursor_offset_from_end,
        )

    def _paste_after_hide(
        self,
        target: windows.WindowIdentity,
        text: str,
        cursor_offset_from_end: int | None = None,
    ) -> None:
        """Paste after native window activation has settled."""
        try:
            pending = clipboard_paste.paste_text(target, text)
        except clipboard_paste.PasteError as error:
            self._reveal_after_error(
                format_user_error(error),
                # Translators: Title of an error inserting a snippet externally.
                _("Paste error"),
            )
            return
        try:
            if cursor_offset_from_end is not None:
                keyboard_input.move_cursor_left(cursor_offset_from_end)
        except clipboard_paste.PasteError as error:
            self.schedule_restore(pending)
            self._reveal_after_error(
                format_user_error(error),
                # Translators: Title for a failed cursor instruction after paste.
                _("Cursor movement error"),
            )
            return
        self.schedule_restore(pending)

    def schedule_restore(
        self,
        pending: clipboard_paste.PendingPaste,
    ) -> None:
        """Schedule restoration of clipboard contents retained by a paste."""
        wx.CallLater(
            CLIPBOARD_RESTORE_DELAY_MS,
            self._restore_clipboard,
            pending,
            CLIPBOARD_RESTORE_ATTEMPTS,
        )

    def _restore_clipboard(
        self,
        pending: clipboard_paste.PendingPaste,
        attempts_remaining: int,
    ) -> None:
        """Restore the saved clipboard, retrying transient access failures."""
        try:
            pending.restore_clipboard()
        except clipboard_paste.PasteError as error:
            if attempts_remaining > 1:
                wx.CallLater(
                    CLIPBOARD_RESTORE_RETRY_DELAY_MS,
                    self._restore_clipboard,
                    pending,
                    attempts_remaining - 1,
                )
                return
            pending.discard_snapshot()
            self._reveal_after_error(
                # Translators: Error after inserting a snippet when restoring the
                # user's old clipboard repeatedly failed. {} is a technical error.
                _(
                    "The previous clipboard contents could not be restored "
                    "after multiple attempts. The clipboard may still contain "
                    "the inserted snippet.\n\n{}"
                ).format(error),
                # Translators: Title of an error restoring the user's clipboard
                # after a snippet was inserted.
                _("Clipboard restore error"),
            )
