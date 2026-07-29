"""Settings dialog with keyboard-accessible global-hotkey recording."""

from collections.abc import Callable
import sys

import wx

from core.error_messages import format_user_error
from core.shortcuts import DEFAULT_TOGGLE_HOTKEY, Hotkey
from i18n import SYSTEM_LANGUAGE, _, get_language_display_name
from ui.shortcut_display import format_hotkey


class FocusableReadOnlyTextCtrl(wx.TextCtrl):
    """Read-only text that remains reachable during keyboard navigation."""
    def __init__(self, parent, value: str = ""):
        """Create a read-only control that still participates in tab order."""
        super().__init__(parent, value=value, style=wx.TE_READONLY)

    def AcceptsFocusFromKeyboard(self) -> bool:
        """Keep the hotkey display reachable to keyboard users."""
        return self.IsEnabled() and self.IsShown()


class SettingsDialog(wx.Dialog):
    """Edit general settings and the global window-toggle hotkey."""
    def __init__(
        self,
        parent,
        current_hotkey: Hotkey,
        current_language: str,
        include_copied_text_in_clipboard_history: bool,
        allow_copied_text_cloud_upload: bool,
        hotstrings_enabled: bool,
        preserve_hotstring_boundary: bool,
        notify_hotstring_expansion: bool,
        available_languages: tuple[str, ...],
        apply_settings: Callable[[Hotkey, str, bool, bool, bool, bool, bool], bool],
        begin_recording: Callable[[], None],
        end_recording: Callable[[], None],
    ):
        """Build settings pages and install hotkey-recording callbacks."""
        super().__init__(
            parent,
            # Translators: Window title for application settings.
            title=_("Settings"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._current_hotkey = current_hotkey
        self._candidate_hotkey = current_hotkey
        self._current_language = current_language
        self._candidate_language = current_language
        self._current_include_copied_text_in_clipboard_history = (
            include_copied_text_in_clipboard_history
        )
        self._candidate_include_copied_text_in_clipboard_history = (
            include_copied_text_in_clipboard_history
        )
        self._current_allow_copied_text_cloud_upload = (
            allow_copied_text_cloud_upload
        )
        self._candidate_allow_copied_text_cloud_upload = (
            allow_copied_text_cloud_upload
        )
        self._current_hotstrings_enabled = hotstrings_enabled
        self._candidate_hotstrings_enabled = hotstrings_enabled
        self._current_preserve_hotstring_boundary = preserve_hotstring_boundary
        self._candidate_preserve_hotstring_boundary = preserve_hotstring_boundary
        self._current_notify_hotstring_expansion = notify_hotstring_expansion
        self._candidate_notify_hotstring_expansion = notify_hotstring_expansion
        self._available_languages = available_languages
        self._apply_settings = apply_settings
        self._begin_recording = begin_recording
        self._end_recording = end_recording
        self._recording = False

        self.notebook = wx.Notebook(self)
        self.general_page = self._create_general_page(self.notebook)
        # Translators: Tab for general application settings such as language.
        # "&" marks the keyboard mnemonic.
        self.notebook.AddPage(self.general_page, _("&General"))
        self.hotstrings_page = self._create_hotstrings_page(self.notebook)
        # Translators: Tab for configuring automatic snippet hotstrings.
        # "&" marks the keyboard mnemonic.
        self.notebook.AddPage(self.hotstrings_page, _("&Hotstrings"))
        self.hotkey_page = self._create_hotkey_page(self.notebook)
        # Translators: Tab for configuring the global keyboard shortcut.
        # "&" marks the keyboard mnemonic.
        self.notebook.AddPage(self.hotkey_page, _("&Keyboard"))

        # Translators: Settings-dialog button that saves pending changes and
        # closes the dialog. "&" marks the keyboard mnemonic.
        self.ok_button = wx.Button(self, wx.ID_OK, _("&OK"))
        # Translators: Settings-dialog button that discards pending changes and
        # closes the dialog. "&" marks the keyboard mnemonic.
        self.cancel_button = wx.Button(self, wx.ID_CANCEL, _("&Cancel"))
        # Translators: Settings-dialog button that saves and activates pending
        # changes without closing the dialog. "&" marks the keyboard mnemonic.
        self.apply_button = wx.Button(self, wx.ID_APPLY, _("&Apply"))
        self.apply_button.Enable(False)

        button_sizer = wx.StdDialogButtonSizer()
        button_sizer.AddButton(self.ok_button)
        button_sizer.AddButton(self.cancel_button)
        button_sizer.AddButton(self.apply_button)
        button_sizer.Realize()

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 10)
        dialog_sizer.Add(
            button_sizer,
            0,
            wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            10,
        )
        self.SetSizer(dialog_sizer)
        self.SetMinSize(self.FromDIP((620, 430)))
        self.SetSize(self.FromDIP((720, 500)))
        self.CentreOnParent()

        self.Bind(wx.EVT_CHAR_HOOK, self._on_character)
        self.ok_button.Bind(wx.EVT_BUTTON, self._on_ok)
        self.apply_button.Bind(wx.EVT_BUTTON, self._on_apply)

    def _create_general_page(self, notebook: wx.Notebook) -> wx.Panel:
        """Create controls for selecting the user-interface language."""
        page = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        # Translators: Label for the user-interface language selector.
        # "&" marks the keyboard mnemonic for the adjacent choice control.
        language_label = wx.StaticText(page, label=_("&Language"))
        language_values = (
            SYSTEM_LANGUAGE,
            *self._available_languages,
        )
        language_labels = tuple(
            get_language_display_name(language, wx)
            for language in language_values
        )
        self.language_choice = wx.Choice(page, choices=language_labels)
        try:
            selection = language_values.index(self._candidate_language)
        except ValueError:
            selection = 0
        self.language_choice.SetSelection(selection)
        self.language_choice.Bind(wx.EVT_CHOICE, self._on_language_changed)
        self._language_values = language_values

        restart_note = wx.StaticText(
            page,
            # Translators: Explains that a newly selected interface language is
            # loaded the next time the application starts.
            label=_("Language changes take effect after restarting btText."),
        )
        restart_note.Wrap(540)

        self.clipboard_history_checkbox = wx.CheckBox(
            page,
            # Translators: General setting that controls whether text copied from
            # a snippet is added to the Windows clipboard history. "&" marks the
            # keyboard mnemonic.
            label=_(
                "Include copied snippet &text in the Windows clipboard history"
            ),
        )
        self.clipboard_history_checkbox.SetValue(
            self._candidate_include_copied_text_in_clipboard_history
        )
        self.clipboard_history_checkbox.Bind(
            wx.EVT_CHECKBOX,
            self._on_clipboard_history_changed,
        )
        self.cloud_clipboard_checkbox = wx.CheckBox(
            page,
            # Translators: General setting that controls whether copied snippet
            # text may be synchronized through the Windows cloud clipboard.
            # "&" marks the keyboard mnemonic.
            label=_(
                "Allow copied snippet text to be stored in the Windows &cloud"
            ),
        )
        self.cloud_clipboard_checkbox.SetValue(
            self._candidate_allow_copied_text_cloud_upload
        )
        self.cloud_clipboard_checkbox.Bind(
            wx.EVT_CHECKBOX,
            self._on_cloud_clipboard_changed,
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(language_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        sizer.Add(
            self.language_choice,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )
        sizer.Add(
            restart_note,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )
        sizer.Add(
            self.clipboard_history_checkbox,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )
        sizer.Add(
            self.cloud_clipboard_checkbox,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )
        page.SetSizer(sizer)
        return page

    def _create_hotstrings_page(self, notebook: wx.Notebook) -> wx.Panel:
        """Create controls for automatic snippet expansion."""
        page = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        description = wx.StaticText(
            page,
            # Translators: Explanation on the hotstring settings page.
            label=_(
                "Hotstrings expand a snippet after its abbreviation is followed "
                "by Space, Enter, Tab, or punctuation."
            ),
        )
        description.Wrap(540)
        self.hotstrings_checkbox = wx.CheckBox(
            page,
            # Translators: Setting that enables automatic expansion of snippet
            # hotstrings. "&" marks the keyboard mnemonic.
            label=_("&Enable hotstrings"),
        )
        self.hotstrings_checkbox.SetValue(self._candidate_hotstrings_enabled)
        self.hotstrings_checkbox.Bind(
            wx.EVT_CHECKBOX, self._on_hotstrings_changed
        )
        self.preserve_hotstring_boundary_checkbox = wx.CheckBox(
            page,
            # Translators: Hotstring setting that keeps the typed Space, Enter,
            # Tab, or punctuation after the expanded snippet.
            label=_("&Keep the ending character after expansion"),
        )
        self.preserve_hotstring_boundary_checkbox.SetValue(
            self._candidate_preserve_hotstring_boundary
        )
        self.preserve_hotstring_boundary_checkbox.Bind(
            wx.EVT_CHECKBOX,
            self._on_preserve_hotstring_boundary_changed,
        )
        self.notify_hotstring_expansion_checkbox = wx.CheckBox(
            page,
            # Translators: Hotstring setting that shows a Windows notification
            # after a snippet was expanded. "&" marks the keyboard mnemonic.
            label=_("Show a Windows &notification after expansion"),
        )
        self.notify_hotstring_expansion_checkbox.SetValue(
            self._candidate_notify_hotstring_expansion
        )
        self.notify_hotstring_expansion_checkbox.Bind(
            wx.EVT_CHECKBOX,
            self._on_notify_hotstring_expansion_changed,
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(description, 0, wx.EXPAND | wx.ALL, 12)
        sizer.Add(
            self.hotstrings_checkbox,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )
        sizer.Add(
            self.preserve_hotstring_boundary_checkbox,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )
        sizer.Add(
            self.notify_hotstring_expansion_checkbox,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )
        page.SetSizer(sizer)
        return page

    def _on_language_changed(self, event: wx.CommandEvent):
        """Store the pending language selected in the choice control."""
        selection = self.language_choice.GetSelection()
        if selection != wx.NOT_FOUND:
            self._candidate_language = self._language_values[selection]
        self._update_apply_button()

    def _on_clipboard_history_changed(self, event: wx.CommandEvent):
        """Store whether copied snippet text may enter clipboard history."""
        self._candidate_include_copied_text_in_clipboard_history = (
            self.clipboard_history_checkbox.GetValue()
        )
        self._update_apply_button()

    def _on_cloud_clipboard_changed(self, event: wx.CommandEvent):
        """Store whether copied snippet text may enter the cloud clipboard."""
        self._candidate_allow_copied_text_cloud_upload = (
            self.cloud_clipboard_checkbox.GetValue()
        )
        self._update_apply_button()

    def _on_hotstrings_changed(self, event: wx.CommandEvent):
        """Store whether automatic hotstring expansion is enabled."""
        self._candidate_hotstrings_enabled = self.hotstrings_checkbox.GetValue()
        self._update_apply_button()

    def _on_preserve_hotstring_boundary_changed(self, event: wx.CommandEvent):
        """Store whether the typed expansion boundary should be replayed."""
        self._candidate_preserve_hotstring_boundary = (
            self.preserve_hotstring_boundary_checkbox.GetValue()
        )
        self._update_apply_button()

    def _on_notify_hotstring_expansion_changed(self, event: wx.CommandEvent):
        """Store whether successful expansions should show a notification."""
        self._candidate_notify_hotstring_expansion = (
            self.notify_hotstring_expansion_checkbox.GetValue()
        )
        self._update_apply_button()

    def _update_apply_button(self):
        """Enable Apply whenever either setting differs from its saved value."""
        self.apply_button.Enable(
            self._candidate_hotkey != self._current_hotkey
            or self._candidate_language != self._current_language
            or self._candidate_include_copied_text_in_clipboard_history
            != self._current_include_copied_text_in_clipboard_history
            or self._candidate_allow_copied_text_cloud_upload
            != self._current_allow_copied_text_cloud_upload
            or self._candidate_hotstrings_enabled
            != self._current_hotstrings_enabled
            or self._candidate_preserve_hotstring_boundary
            != self._current_preserve_hotstring_boundary
            or self._candidate_notify_hotstring_expansion
            != self._current_notify_hotstring_expansion
        )

    def _create_hotkey_page(self, notebook: wx.Notebook) -> wx.Panel:
        """Create controls for displaying and recording the global hotkey."""
        page = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        description = wx.StaticText(
            page,
            # Translators: Settings-page explanation of the global shortcut and
            # its required modifier keys.
            label=_(
                "Configure the global shortcut used to show or hide the main "
                "window. A shortcut must contain Ctrl, Shift, Alt or the "
                "Windows key."
            ),
        )
        description.Wrap(540)

        # Translators: Label for the currently configured global shortcut.
        # "&" marks the keyboard mnemonic for the adjacent read-only field.
        hotkey_label = wx.StaticText(page, label=_("Current &hotkey"))
        self.hotkey_display = FocusableReadOnlyTextCtrl(
            page,
            value=format_hotkey(self._candidate_hotkey),
        )
        self.hotkey_display.SetName(
            # Translators: Accessible name for the read-only field displaying
            # the currently configured global show-or-hide shortcut.
            _("Current show or hide window shortcut")
        )

        self.record_button = wx.Button(
            page,
            # Translators: Button that starts listening for a new global
            # shortcut. "&" marks the keyboard mnemonic.
            label=_("&Record new shortcut"),
        )
        self.record_button.Bind(wx.EVT_BUTTON, self._start_recording)
        self.cancel_recording_button = wx.Button(
            page,
            # Translators: Button that stops the current shortcut recording
            # without accepting it. "&" marks the keyboard mnemonic.
            label=_("Cancel &recording"),
        )
        self.cancel_recording_button.Enable(False)
        self.cancel_recording_button.Bind(
            wx.EVT_BUTTON,
            self._cancel_recording,
        )
        # Translators: Button that selects btText's default global shortcut as
        # the pending setting. "&" marks the keyboard mnemonic.
        default_button = wx.Button(page, label=_("Use &default"))
        default_button.Bind(wx.EVT_BUTTON, self._use_default)
        self.hotkey_display.MoveBeforeInTabOrder(self.record_button)

        self.recording_status = wx.StaticText(
            page,
            # Translators: Initial status before shortcut recording starts.
            label=_("Recording is not active."),
        )
        # Translators: Accessible name for the text that reports shortcut
        # recording instructions and results.
        self.recording_status.SetName(_("Shortcut recording status"))

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.Add(self.record_button, 0, wx.RIGHT, 8)
        button_sizer.Add(self.cancel_recording_button, 0, wx.RIGHT, 8)
        button_sizer.Add(default_button)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(description, 0, wx.EXPAND | wx.ALL, 12)
        sizer.Add(hotkey_label, 0, wx.LEFT | wx.RIGHT, 12)
        sizer.Add(
            self.hotkey_display,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )
        sizer.Add(button_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        sizer.Add(
            self.recording_status,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )
        page.SetSizer(sizer)
        return page

    def _start_recording(self, event: wx.CommandEvent):
        """Suspend the global binding and begin capturing key events."""
        # Release the global registration while the dialog captures its keys.
        if self._recording:
            return
        self._begin_recording()
        self._recording = True
        # Translators: Temporary button label while btText waits for the user to
        # press a new global shortcut.
        self.record_button.SetLabel(_("Press shortcut now"))
        self.record_button.SetName(
            # Translators: Accessible name while btText is waiting for a shortcut;
            # Escape cancels and Tab leaves the recording control.
            _(
                "Recording shortcut. Press Escape to cancel or Tab to leave "
                "recording."
            )
        )
        self.cancel_recording_button.Enable(True)
        self.recording_status.SetLabel(
            # Translators: Instructions shown while recording a new global
            # shortcut. Keep Escape, Tab, and Shift+Tab recognizable key names.
            _(
                "Press one shortcut now. Escape cancels; Tab and Shift+Tab "
                "remain available."
            )
        )
        self.recording_status.Wrap(540)
        self.record_button.SetFocus()

    def _cancel_recording(self, event=None):
        """Cancel recording and retain the previously selected hotkey."""
        if not self._recording:
            return
        # Translators: Status after the user cancels shortcut recording.
        self._finish_recording(_("Shortcut recording cancelled."))

    def _finish_recording(self, status: str):
        """Leave recording mode, resume the binding, and report status."""
        was_recording = self._recording
        self._recording = False
        # Translators: Button label restored after shortcut recording ends; it
        # starts listening for another shortcut. "&" marks the mnemonic.
        self.record_button.SetLabel(_("&Record new shortcut"))
        # Translators: Accessible button name restored after recording ends; the
        # button starts recording another global shortcut.
        self.record_button.SetName(_("Record new shortcut"))
        self.cancel_recording_button.Enable(False)
        self.recording_status.SetLabel(status)
        self.recording_status.Wrap(540)
        if was_recording:
            self._end_recording()

    def _on_character(self, event: wx.KeyEvent):
        """Interpret one captured key event as navigation or a hotkey."""
        if not self._recording:
            if self._handle_hotkey_display_navigation(event):
                return
            event.Skip()
            return

        key_code = event.GetKeyCode()
        if key_code == wx.WXK_ESCAPE:
            self._cancel_recording()
            return
        if key_code == wx.WXK_TAB:
            self._cancel_recording()
            event.Skip()
            return
        if event.AltDown() and key_code == wx.WXK_F4:
            self._cancel_recording()
            event.Skip()
            return
        if self._is_modifier_event(event):
            return

        key_name = self._get_key_name_from_event(event)
        try:
            if key_name is None:
                raise ValueError("The pressed key is not supported")
            hotkey = Hotkey(
                key=key_name,
                control=event.ControlDown(),
                shift=event.ShiftDown(),
                alt=event.AltDown(),
                windows=self._windows_down(event),
            )
        except ValueError as error:
            wx.Bell()
            self._finish_recording(
                # Translators: Status announced after an invalid shortcut ends
                # recording. {error} explains why the key was rejected.
                _(
                    "Shortcut not accepted: {error}. Recording has stopped."
                ).format(error=format_user_error(error))
            )
            return

        self._candidate_hotkey = hotkey
        self.hotkey_display.SetValue(format_hotkey(hotkey))
        self._update_apply_button()
        self._finish_recording(
            # Translators: Status after recording succeeds. The shortcut is not
            # active until Apply or OK saves it. {shortcut} is such as Ctrl+Alt+T.
            _(
                "Shortcut {shortcut} recorded. Choose Apply or OK to activate "
                "it."
            ).format(shortcut=format_hotkey(hotkey))
        )

    def _handle_hotkey_display_navigation(self, event: wx.KeyEvent) -> bool:
        """Provide explicit Tab navigation while the display captures keys."""
        if event.GetKeyCode() != wx.WXK_TAB:
            return False

        focused_window = wx.Window.FindFocus()
        keyboard_page_selected = (
            self.notebook.GetCurrentPage() is self.hotkey_page
        )
        if (
            keyboard_page_selected
            and focused_window is self.notebook
            and not event.ShiftDown()
        ):
            self.hotkey_display.SetFocus()
            return True
        if focused_window is self.record_button and event.ShiftDown():
            self.hotkey_display.SetFocus()
            return True
        if focused_window is self.hotkey_display:
            if event.ShiftDown():
                self.notebook.SetFocus()
            else:
                self.record_button.SetFocus()
            return True
        return False

    @staticmethod
    def _get_key_name(key_code: int) -> str | None:
        """Map common wx key codes to stable serialized names."""
        if ord("A") <= key_code <= ord("Z"):
            return chr(key_code)
        if ord("0") <= key_code <= ord("9"):
            return chr(key_code)
        if wx.WXK_F1 <= key_code <= wx.WXK_F24:
            return "F{}".format(key_code - wx.WXK_F1 + 1)
        return None

    @staticmethod
    def _is_modifier_event(event: wx.KeyEvent) -> bool:
        """Return whether an event represents only a modifier key."""
        modifier_keys = {
            wx.WXK_CONTROL,
            wx.WXK_SHIFT,
            wx.WXK_ALT,
            getattr(wx, "WXK_RAW_CONTROL", wx.WXK_CONTROL),
            getattr(wx, "WXK_COMMAND", wx.WXK_CONTROL),
            getattr(wx, "WXK_WINDOWS_LEFT", wx.WXK_CONTROL),
            getattr(wx, "WXK_WINDOWS_RIGHT", wx.WXK_CONTROL),
        }
        # Windows uses separate virtual-key codes for left and right modifier
        # keys in raw keyboard events.
        raw_modifier_keys = {
            0xA0,  # VK_LSHIFT
            0xA1,  # VK_RSHIFT
            0xA2,  # VK_LCONTROL
            0xA3,  # VK_RCONTROL
            0xA4,  # VK_LMENU (Alt)
            0xA5,  # VK_RMENU (Alt/AltGr)
        }
        return (
            event.GetKeyCode() in modifier_keys
            or event.GetRawKeyCode() in raw_modifier_keys
        )

    @classmethod
    def _get_key_name_from_event(cls, event: wx.KeyEvent) -> str | None:
        """Derive a portable key name from a wx key event."""
        key_code = event.GetKeyCode()
        raw_key_code = event.GetRawKeyCode()

        try:
            return Hotkey.key_from_code(raw_key_code)
        except ValueError:
            pass

        # With Ctrl held down, wx can report letters as ASCII control codes
        # (Ctrl+A == 1 through Ctrl+Z == 26) instead of A through Z.
        if event.ControlDown() and 1 <= key_code <= 26:
            return chr(ord("A") + key_code - 1)

        key_name = cls._get_key_name(key_code)
        if key_name is not None:
            return key_name

        unicode_key = event.GetUnicodeKey()
        if unicode_key != wx.WXK_NONE:
            key_name = cls._get_key_name(unicode_key)
            if key_name is not None:
                return key_name

        # On Windows this is the virtual-key code and remains stable when
        # Ctrl and Alt transform GetKeyCode() into a control character.
        return cls._get_key_name(raw_key_code)

    @staticmethod
    def _windows_down(event: wx.KeyEvent) -> bool:
        """Return whether either Windows key is currently pressed."""
        if event.MetaDown() or bool(event.GetModifiers() & wx.MOD_WIN):
            return True

        for key_name in ("WXK_WINDOWS_LEFT", "WXK_WINDOWS_RIGHT"):
            key_code = getattr(wx, key_name, None)
            if key_code is not None and wx.GetKeyState(key_code):
                return True

        if sys.platform == "win32":
            from ctypes import windll

            left_windows_key = windll.user32.GetAsyncKeyState(0x5B)
            right_windows_key = windll.user32.GetAsyncKeyState(0x5C)
            return bool(
                left_windows_key & 0x8000
                or right_windows_key & 0x8000
            )
        return False

    def _use_default(self, event: wx.CommandEvent):
        """Reset the pending hotkey to the application default."""
        self._cancel_recording()
        self._candidate_hotkey = DEFAULT_TOGGLE_HOTKEY
        self.hotkey_display.SetValue(
            format_hotkey(self._candidate_hotkey)
        )
        self._update_apply_button()
        self.recording_status.SetLabel(
            # Translators: Status after selecting btText's default shortcut; it
            # is only activated when Apply or OK saves the setting.
            _(
                "Default shortcut selected. Choose Apply or OK to activate it."
            )
        )

    def _apply(self) -> bool:
        """Apply all pending settings through the main-frame callback."""
        self._cancel_recording()
        if (
            self._candidate_hotkey == self._current_hotkey
            and self._candidate_language == self._current_language
            and self._candidate_include_copied_text_in_clipboard_history
            == self._current_include_copied_text_in_clipboard_history
            and self._candidate_allow_copied_text_cloud_upload
            == self._current_allow_copied_text_cloud_upload
            and self._candidate_hotstrings_enabled
            == self._current_hotstrings_enabled
            and self._candidate_preserve_hotstring_boundary
            == self._current_preserve_hotstring_boundary
            and self._candidate_notify_hotstring_expansion
            == self._current_notify_hotstring_expansion
        ):
            return True
        if not self._apply_settings(
            self._candidate_hotkey,
            self._candidate_language,
            self._candidate_include_copied_text_in_clipboard_history,
            self._candidate_allow_copied_text_cloud_upload,
            self._candidate_hotstrings_enabled,
            self._candidate_preserve_hotstring_boundary,
            self._candidate_notify_hotstring_expansion,
        ):
            return False
        self._current_hotkey = self._candidate_hotkey
        self._current_language = self._candidate_language
        self._current_include_copied_text_in_clipboard_history = (
            self._candidate_include_copied_text_in_clipboard_history
        )
        self._current_allow_copied_text_cloud_upload = (
            self._candidate_allow_copied_text_cloud_upload
        )
        self._current_hotstrings_enabled = self._candidate_hotstrings_enabled
        self._current_preserve_hotstring_boundary = (
            self._candidate_preserve_hotstring_boundary
        )
        self._current_notify_hotstring_expansion = (
            self._candidate_notify_hotstring_expansion
        )
        self.apply_button.Enable(False)
        # Translators: Status confirming that all pending application settings
        # were saved and activated where possible.
        self.recording_status.SetLabel(_("The settings have been applied."))
        return True

    def _on_apply(self, event: wx.CommandEvent):
        """Apply settings without closing the dialog."""
        self._apply()

    def _on_ok(self, event: wx.CommandEvent):
        """Apply settings and close only when the change succeeds."""
        if self._apply():
            self.EndModal(wx.ID_OK)

    def Destroy(self):
        """Resume the global hotkey before destroying the dialog."""
        self._cancel_recording()
        return super().Destroy()
