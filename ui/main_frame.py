import pymitter
import wx
import wx.adv
import wx.lib.sized_controls as sc

import clipboard_paste
import datamodel
import info
from app_settings import AppSettings, Hotkey, SettingsError, SettingsStore
from ui import utils
from ui.category_list import CategoryList
from ui.search_dialog import SearchDialog
from ui.settings_dialog import SettingsDialog
from ui.snippet_list import SnippetList
from ui.tray_icon import TrayIcon
from ui.transfer import TransferBuffer

CLIPBOARD_RESTORE_DELAY_MS = 500


class MainFrame(sc.SizedFrame):
    def __init__(
        self,
        ee: pymitter.EventEmitter,
        model: datamodel.DataModel,
        settings_store: SettingsStore,
        settings: AppSettings,
    ):
        super().__init__(None, title=wx.GetApp().GetAppName())
        self._ee = ee
        self._model = model
        self._settings_store = settings_store
        self._settings = settings
        self._hotkey_id = 1
        self._registered_hotkey = None
        self._hotkey_suspended = False
        foreground_window = clipboard_paste.get_foreground_window()
        self._paste_target_window = (
            foreground_window
            if clipboard_paste.is_external_window(foreground_window)
            else None
        )
        self._ee.on("snippet.insert_requested", self.insert_snippet)
        self._ee.on("status.changed", self.set_status_text)
        self.Bind(wx.EVT_ACTIVATE, self.on_activate)
        self.Bind(wx.EVT_HOTKEY, self.on_global_hotkey, id=self._hotkey_id)
        self.pane = self.GetContentsPane()
        self.pane.SetSizerType("horizontal")
        self.transfer_buffer = TransferBuffer()
        self.category_list_label = wx.StaticText(self.pane, label="&Categories")
        self.category_list = CategoryList(
            self.pane,
            ee,
            model,
            self.transfer_buffer,
        )
        self.category_list.SetSizerProps(expand=True, proportion=1)  # type: ignore
        self.snippet_list_label = wx.StaticText(self.pane, label="&Snippets")
        self.snippet_list = SnippetList(
            self.pane,
            ee,
            model,
            self.transfer_buffer,
        )
        self.snippet_list.SetSizerProps(expand=True, proportion=1)  # type: ignore
        self._last_focused_control: wx.Window | None = None
        self._search_command_id = wx.NewIdRef()
        self._settings_command_id = wx.NewIdRef()
        self.Bind(
            wx.EVT_MENU,
            self.on_search,
            id=int(self._search_command_id),
        )
        self.Bind(
            wx.EVT_MENU,
            self.on_settings,
            id=int(self._settings_command_id),
        )
        self._create_menubar()
        self._create_statusbar()
        self._create_tray_icon()
        self._register_hotkey(self._settings.toggle_window_hotkey)

    def on_search(self, event: wx.CommandEvent):
        selected_snippet = None
        with utils.managed_dialog(SearchDialog(self, self._model)) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            try:
                selected_snippet = dialog.get_selected_snippet()
            except datamodel.DataModelError as error:
                wx.MessageBox(
                    str(error),
                    "Error",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
                return

        if selected_snippet is not None:
            self.focus_snippet(selected_snippet)

    def focus_snippet(self, snippet: datamodel.Snippet):
        if snippet.id is None:
            return
        if not self.category_list.focus_id(snippet.category_id):
            wx.MessageBox(
                "The category of the selected snippet no longer exists.",
                "Error",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self.snippet_list.update(snippet.category_id, force=True)
        if not self.snippet_list.focus_id(snippet.id):
            wx.MessageBox(
                "The selected snippet no longer exists.",
                "Error",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self.snippet_list.SetFocus()

    def _register_hotkey(self, hotkey: Hotkey, show_error: bool = True) -> bool:
        success = self.RegisterHotKey(
            self._hotkey_id,
            self._get_hotkey_modifiers(hotkey),
            self._get_hotkey_key_code(hotkey),
        )
        if not success:
            if show_error:
                wx.MessageBox(
                    "The global hotkey {} is already in use and could not be registered.".format(
                        hotkey.to_display_string()
                    ),
                    "Hotkey error",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
            return False
        self._registered_hotkey = hotkey
        return True

    @staticmethod
    def _get_hotkey_modifiers(hotkey: Hotkey) -> int:
        modifiers = 0
        if hotkey.control:
            modifiers |= wx.MOD_CONTROL
        if hotkey.shift:
            modifiers |= wx.MOD_SHIFT
        if hotkey.alt:
            modifiers |= wx.MOD_ALT
        if hotkey.windows:
            modifiers |= wx.MOD_WIN
        return modifiers

    @staticmethod
    def _get_hotkey_key_code(hotkey: Hotkey) -> int:
        return hotkey.key_code

    def _unregister_hotkey(self):
        if self._registered_hotkey is None:
            return
        self.UnregisterHotKey(self._hotkey_id)
        self._registered_hotkey = None

    def _suspend_hotkey(self):
        self._hotkey_suspended = True
        self._unregister_hotkey()

    def _resume_hotkey(self):
        if not self._hotkey_suspended:
            return
        self._hotkey_suspended = False
        if self._registered_hotkey is None:
            self._register_hotkey(self._settings.toggle_window_hotkey)

    def _change_hotkey(self, hotkey: Hotkey) -> bool:
        old_hotkey = self._settings.toggle_window_hotkey
        self._unregister_hotkey()
        if not self._register_hotkey(hotkey, show_error=False):
            restored = self._register_hotkey(old_hotkey, show_error=False)
            if restored:
                message = (
                    "The selected hotkey {} is already in use. "
                    "The previous hotkey has been restored."
                ).format(hotkey.to_display_string())
            else:
                message = (
                    "The selected hotkey {} is already in use and the previous "
                    "hotkey could not be restored. No global hotkey is active."
                ).format(hotkey.to_display_string())
            wx.MessageBox(
                message,
                "Hotkey error",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return False

        new_settings = AppSettings(toggle_window_hotkey=hotkey)
        try:
            self._settings_store.save(new_settings)
        except SettingsError as error:
            self._unregister_hotkey()
            restored = self._register_hotkey(old_hotkey, show_error=False)
            if not restored:
                wx.MessageBox(
                    "The previous hotkey could not be restored. No global hotkey is active.",
                    "Hotkey error",
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
            wx.MessageBox(
                str(error),
                "Settings error",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return False
        self._settings = new_settings
        return True

    def on_global_hotkey(self, event):
        if self.IsShown():
            self._remember_focused_control()
            self.Hide()
        else:
            self._remember_foreground_window()
            self.show_and_focus()

    def show_and_focus(self):
        self.Show()
        self.Iconize(False)
        self.Raise()
        target = self._last_focused_control or self.category_list
        target.SetFocus()
        wx.CallAfter(target.SetFocus)

    def _remember_focused_control(self):
        focused_control = wx.Window.FindFocus()
        if focused_control in (self.category_list, self.snippet_list):
            self._last_focused_control = focused_control

    def on_activate(self, event: wx.ActivateEvent):
        event.Skip()
        if not event.GetActive():
            self._remember_focused_control()
            wx.CallAfter(self._remember_foreground_window)

    def _remember_foreground_window(self):
        foreground_window = clipboard_paste.get_foreground_window()
        if clipboard_paste.is_external_window(foreground_window):
            self._paste_target_window = foreground_window

    def insert_snippet(self, snippet_id: int):
        if self._paste_target_window is None:
            wx.MessageBox(
                "There is no previous window to insert the snippet into.",
                "Paste error",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        try:
            snippet = self._model.get_snippet(snippet_id)
        except datamodel.DataModelError as error:
            wx.MessageBox(str(error), "Error", wx.OK | wx.ICON_ERROR, self)
            return

        self._remember_focused_control()
        self.Hide()
        wx.CallLater(50, self._paste_after_hide, snippet.content)

    def _paste_after_hide(self, text: str):
        try:
            pending = clipboard_paste.paste_text(self._paste_target_window, text)
        except clipboard_paste.PasteError as error:
            self.Show()
            self.Iconize(False)
            wx.MessageBox(str(error), "Paste error", wx.OK | wx.ICON_ERROR, self)
            return
        wx.CallLater(
            CLIPBOARD_RESTORE_DELAY_MS,
            self._restore_clipboard,
            pending,
            3,
        )

    def _restore_clipboard(
        self,
        pending: clipboard_paste.PendingPaste,
        attempts_remaining: int,
    ):
        try:
            pending.restore_clipboard()
        except clipboard_paste.PasteError as error:
            if attempts_remaining > 1:
                wx.CallLater(
                    100,
                    self._restore_clipboard,
                    pending,
                    attempts_remaining - 1,
                )
                return
            pending.discard_snapshot()
            wx.MessageBox(
                "The previous clipboard contents could not be restored after "
                "multiple attempts. The clipboard may still contain the inserted "
                "snippet.\n\n{}".format(error),
                "Clipboard restore error",
                wx.OK | wx.ICON_ERROR,
                self,
            )

    def _create_menubar(self):
        menubar = wx.MenuBar()
        edit_menu = wx.Menu()
        edit_menu.Append(int(self._search_command_id), "&Search...\tF3")
        edit_menu.AppendSeparator()
        edit_menu.Append(int(self._settings_command_id), "&Settings...\tCtrl+,")
        menubar.Append(edit_menu, "&Edit")
        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "About")
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        menubar.Append(help_menu, "&Help")
        self.SetMenuBar(menubar)

    def on_settings(self, event: wx.CommandEvent):
        with utils.managed_dialog(
            SettingsDialog(
                self,
                self._settings.toggle_window_hotkey,
                self._change_hotkey,
                self._suspend_hotkey,
                self._resume_hotkey,
            )
        ) as dialog:
            dialog.ShowModal()

    def _create_statusbar(self):
        self.status_bar = self.CreateStatusBar()

    def set_status_text(self, message: str):
        self.status_bar.SetStatusText(message)

    def on_about(self, event: wx.CommandEvent):
        about_info = wx.adv.AboutDialogInfo()
        about_info.AddDeveloper(info.author)
        about_info.SetName(info.name)
        about_info.SetVersion(info.version)
        wx.adv.AboutBox(about_info)

    def _create_tray_icon(self):
        self.allow_close = False
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.tray_icon = TrayIcon(self)

    def on_close(self, event: wx.CloseEvent):
        if self.allow_close:
            self._unregister_hotkey()
            self.tray_icon.RemoveIcon()
            self.tray_icon.Destroy()
            event.Skip()
        else:
            self.Hide()
            event.Veto()
