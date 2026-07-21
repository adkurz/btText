from collections.abc import Callable
import sys

import wx

from app_settings import DEFAULT_TOGGLE_HOTKEY, Hotkey


class FocusableReadOnlyTextCtrl(wx.TextCtrl):
    def __init__(self, parent, value: str = ""):
        super().__init__(parent, value=value, style=wx.TE_READONLY)

    def AcceptsFocusFromKeyboard(self) -> bool:
        return self.IsEnabled() and self.IsShown()


class SettingsDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        current_hotkey: Hotkey,
        apply_hotkey: Callable[[Hotkey], bool],
        begin_recording: Callable[[], None],
        end_recording: Callable[[], None],
    ):
        super().__init__(
            parent,
            title="Settings",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._current_hotkey = current_hotkey
        self._candidate_hotkey = current_hotkey
        self._apply_hotkey = apply_hotkey
        self._begin_recording = begin_recording
        self._end_recording = end_recording
        self._recording = False

        self.notebook = wx.Notebook(self)
        self.hotkey_page = self._create_hotkey_page(self.notebook)
        self.notebook.AddPage(self.hotkey_page, "&Keyboard")

        self.ok_button = wx.Button(self, wx.ID_OK, "&OK")
        self.cancel_button = wx.Button(self, wx.ID_CANCEL, "&Cancel")
        self.apply_button = wx.Button(self, wx.ID_APPLY, "&Apply")
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
        self.SetMinSize((620, 430))
        self.SetSize((700, 480))

        self.Bind(wx.EVT_CHAR_HOOK, self._on_character)
        self.ok_button.Bind(wx.EVT_BUTTON, self._on_ok)
        self.apply_button.Bind(wx.EVT_BUTTON, self._on_apply)

    def _create_hotkey_page(self, notebook: wx.Notebook) -> wx.Panel:
        page = wx.Panel(notebook, style=wx.TAB_TRAVERSAL)
        description = wx.StaticText(
            page,
            label=(
                "Configure the global shortcut used to show or hide the main "
                "window. A shortcut must contain Ctrl, Shift, Alt or the "
                "Windows key."
            ),
        )
        description.Wrap(540)

        hotkey_label = wx.StaticText(page, label="Current &hotkey")
        self.hotkey_display = FocusableReadOnlyTextCtrl(
            page,
            value=self._candidate_hotkey.to_display_string(),
        )
        self.hotkey_display.SetName("Current show or hide window shortcut")

        self.record_button = wx.Button(
            page,
            label="&Record new shortcut",
        )
        self.record_button.Bind(wx.EVT_BUTTON, self._start_recording)
        self.cancel_recording_button = wx.Button(
            page,
            label="Cancel &recording",
        )
        self.cancel_recording_button.Enable(False)
        self.cancel_recording_button.Bind(
            wx.EVT_BUTTON,
            self._cancel_recording,
        )
        default_button = wx.Button(page, label="Use &default")
        default_button.Bind(wx.EVT_BUTTON, self._use_default)
        self.hotkey_display.MoveBeforeInTabOrder(self.record_button)

        self.recording_status = wx.StaticText(
            page,
            label="Recording is not active.",
        )
        self.recording_status.SetName("Shortcut recording status")

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
        if self._recording:
            return
        self._begin_recording()
        self._recording = True
        self.record_button.SetLabel("Press shortcut now")
        self.record_button.SetName(
            "Recording shortcut. Press Escape to cancel or Tab to leave recording."
        )
        self.cancel_recording_button.Enable(True)
        self.recording_status.SetLabel(
            "Press one shortcut now. Escape cancels; Tab and Shift+Tab remain available."
        )
        self.recording_status.Wrap(540)
        self.record_button.SetFocus()

    def _cancel_recording(self, event=None):
        if not self._recording:
            return
        self._finish_recording("Shortcut recording cancelled.")

    def _finish_recording(self, status: str):
        was_recording = self._recording
        self._recording = False
        self.record_button.SetLabel("&Record new shortcut")
        self.record_button.SetName("Record new shortcut")
        self.cancel_recording_button.Enable(False)
        self.recording_status.SetLabel(status)
        self.recording_status.Wrap(540)
        if was_recording:
            self._end_recording()

    def _on_character(self, event: wx.KeyEvent):
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
                "Shortcut not accepted: {}. Recording has stopped.".format(
                    error
                )
            )
            return

        self._candidate_hotkey = hotkey
        self.hotkey_display.SetValue(hotkey.to_display_string())
        self.apply_button.Enable(hotkey != self._current_hotkey)
        self._finish_recording(
            "Shortcut {} recorded. Choose Apply or OK to activate it.".format(
                hotkey.to_display_string()
            )
        )

    def _handle_hotkey_display_navigation(self, event: wx.KeyEvent) -> bool:
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
        if ord("A") <= key_code <= ord("Z"):
            return chr(key_code)
        if ord("0") <= key_code <= ord("9"):
            return chr(key_code)
        if wx.WXK_F1 <= key_code <= wx.WXK_F24:
            return "F{}".format(key_code - wx.WXK_F1 + 1)
        return None

    @staticmethod
    def _is_modifier_event(event: wx.KeyEvent) -> bool:
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
        self._cancel_recording()
        self._candidate_hotkey = DEFAULT_TOGGLE_HOTKEY
        self.hotkey_display.SetValue(
            self._candidate_hotkey.to_display_string()
        )
        self.apply_button.Enable(
            self._candidate_hotkey != self._current_hotkey
        )
        self.recording_status.SetLabel(
            "Default shortcut selected. Choose Apply or OK to activate it."
        )

    def _apply(self) -> bool:
        self._cancel_recording()
        if self._candidate_hotkey == self._current_hotkey:
            return True
        if not self._apply_hotkey(self._candidate_hotkey):
            return False
        self._current_hotkey = self._candidate_hotkey
        self.apply_button.Enable(False)
        self.recording_status.SetLabel("The shortcut has been applied.")
        return True

    def _on_apply(self, event: wx.CommandEvent):
        self._apply()

    def _on_ok(self, event: wx.CommandEvent):
        if self._apply():
            self.EndModal(wx.ID_OK)

    def Destroy(self):
        self._cancel_recording()
        return super().Destroy()
