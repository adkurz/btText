"""Main-window coordination for navigation, hotkeys, and external paste."""

import ctypes
from ctypes import wintypes

import pymitter
import wx
import wx.adv
import wx.lib.sized_controls as sc

import clipboard_paste
import datamodel
import hotstrings
import i18n
import info
from app_settings import AppSettings, Hotkey, SettingsError, SettingsStore
from error_messages import format_user_error
from i18n import _
from ui import utils
from ui.category_tree import CategoryTree
from ui.search_dialog import SearchDialog
from ui.settings_dialog import SettingsDialog
from ui.snippet_list import SnippetList
from ui.tray_icon import TrayIcon
from ui.transfer import TransferBuffer

CLIPBOARD_RESTORE_DELAY_MS = 500
HOTKEY_LAYOUT_CHECK_INTERVAL_MS = 500

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
)
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
user32.GetKeyboardLayout.restype = wintypes.HANDLE
user32.ActivateKeyboardLayout.argtypes = (wintypes.HANDLE, wintypes.UINT)
user32.ActivateKeyboardLayout.restype = wintypes.HANDLE


def _get_foreground_keyboard_layout() -> int | None:
    """Return the keyboard layout used by the current foreground thread."""
    foreground_window = user32.GetForegroundWindow()
    if not foreground_window:
        return None
    thread_id = user32.GetWindowThreadProcessId(foreground_window, None)
    if not thread_id:
        return None
    keyboard_layout = user32.GetKeyboardLayout(thread_id)
    return int(keyboard_layout) if keyboard_layout else None


def _activate_keyboard_layout(keyboard_layout: int) -> bool:
    """Activate a foreground thread's keyboard layout for btText's UI thread."""
    return bool(user32.ActivateKeyboardLayout(keyboard_layout, 0))


class MainFrame(sc.SizedFrame):
    """Coordinate the application's views and process-wide integrations."""
    def __init__(
        self,
        ee: pymitter.EventEmitter,
        model: datamodel.DataModel,
        settings_store: SettingsStore,
        settings: AppSettings,
    ):
        """Build the main views and register process-wide event handlers."""
        super().__init__(None, title=wx.GetApp().GetAppName())
        self._ee = ee
        self._model = model
        self._settings_store = settings_store
        self._settings = settings
        self._hotstring_hook = hotstrings.KeyboardHook(
            self._queue_hotstring_expansion,
            lambda: clipboard_paste.is_external_window(
                clipboard_paste.get_foreground_window()
            ),
        )
        self._ee.on("snippet.added", self._refresh_hotstrings)
        self._ee.on("snippet.edited", self._refresh_hotstrings)
        self._ee.on("snippet.deleted", self._refresh_hotstrings)
        self._hotkey_id = 1
        self._registered_hotkey = None
        self._hotkey_suspended = False
        self._hotkey_keyboard_layout = _get_foreground_keyboard_layout()
        self._hotkey_layout_timer = wx.Timer(self)
        self.Bind(
            wx.EVT_TIMER,
            self._on_hotkey_layout_timer,
            self._hotkey_layout_timer,
        )
        self._hotkey_layout_timer.Start(HOTKEY_LAYOUT_CHECK_INTERVAL_MS)
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
        self.transfer_buffer = TransferBuffer()
        layout_panel = wx.Panel(self.pane)
        layout_panel.SetSizerProps(expand=True, proportion=1)  # type: ignore

        self.category_tree_label = wx.StaticText(
            layout_panel,
            # Translators: Heading for the tree used to select a category.
            # "&" marks the keyboard mnemonic for the category tree.
            label=_("&Categories"),
        )
        self._style_section_label(self.category_tree_label)
        self.category_tree = CategoryTree(
            layout_panel,
            ee,
            model,
            self.transfer_buffer,
        )
        # Translators: Accessible name for the main window's category tree.
        self.category_tree.SetName(_("Categories"))
        self.snippet_list_label = wx.StaticText(
            layout_panel,
            # Translators: Heading for the list of snippets in the selected
            # category. "&" marks the keyboard mnemonic for the snippet list.
            label=_("&Snippets"),
        )
        self._style_section_label(self.snippet_list_label)
        self.snippet_list = SnippetList(
            layout_panel,
            ee,
            model,
            self.transfer_buffer,
            lambda: self._settings.include_copied_text_in_clipboard_history,
            lambda: self._settings.allow_copied_text_cloud_upload,
        )
        # Translators: Accessible name for the main window list showing snippets
        # from the selected category.
        self.snippet_list.SetName(_("Snippets in the selected category"))

        main_sizer = wx.GridBagSizer(
            vgap=self.FromDIP(6),
            hgap=self.FromDIP(18),
        )
        main_sizer.Add(
            self.category_tree_label,
            pos=(0, 0),
            flag=wx.LEFT | wx.TOP,
            border=self.FromDIP(12),
        )
        main_sizer.Add(
            self.category_tree,
            pos=(1, 0),
            flag=wx.EXPAND | wx.LEFT | wx.BOTTOM,
            border=self.FromDIP(12),
        )
        main_sizer.Add(
            self.snippet_list_label,
            pos=(0, 1),
            flag=wx.TOP | wx.RIGHT,
            border=self.FromDIP(12),
        )
        main_sizer.Add(
            self.snippet_list,
            pos=(1, 1),
            flag=wx.EXPAND | wx.RIGHT | wx.BOTTOM,
            border=self.FromDIP(12),
        )
        main_sizer.AddGrowableRow(1, 1)
        main_sizer.AddGrowableCol(0, 1)
        main_sizer.AddGrowableCol(1, 2)
        layout_panel.SetSizer(main_sizer)
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
        self._refresh_hotstrings()
        if self._settings.hotstrings_enabled:
            try:
                self._hotstring_hook.start()
            except OSError as error:
                wx.MessageBox(
                    str(error),
                    # Translators: Title for a failure to monitor or expand a
                    # globally typed snippet hotstring.
                    _("Hotstring error"),
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
        self.SetMinSize(self.FromDIP((760, 480)))
        self.SetClientSize(self.FromDIP((1040, 680)))
        self.Centre()

    @staticmethod
    def _style_section_label(label: wx.StaticText):
        """Give a primary view heading the native bold system font."""
        font = wx.Font(label.GetFont())
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        label.SetFont(font)

    def on_search(self, event: wx.CommandEvent):
        """Open search and focus the snippet accepted by the user."""
        selected_snippet = None
        with utils.managed_dialog(SearchDialog(self, self._model)) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            try:
                selected_snippet = dialog.get_selected_snippet()
            except datamodel.DataModelError as error:
                wx.MessageBox(
                    format_user_error(error),
                    # Translators: Generic title for a failed main-window operation.
                    _("Error"),
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
                return

        if selected_snippet is not None:
            self.focus_snippet(selected_snippet)

    def focus_snippet(self, snippet: datamodel.Snippet):
        """Select a snippet and its category in the main views."""
        if snippet.id is None:
            return
        if not self.category_tree.focus_id(snippet.category_id):
            wx.MessageBox(
                # Translators: Error shown when a selected snippet points to a
                # category that was deleted meanwhile.
                _("The category of the selected snippet no longer exists."),
                # Translators: Generic title for a failed main-window operation.
                _("Error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self.snippet_list.update(snippet.category_id, force=True)
        if not self.snippet_list.focus_id(snippet.id):
            wx.MessageBox(
                # Translators: Error shown when the selected snippet was deleted
                # before it could be displayed or inserted.
                _("The selected snippet no longer exists."),
                # Translators: Generic title for a failed main-window operation.
                _("Error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self.snippet_list.SetFocus()

    def _register_hotkey(self, hotkey: Hotkey, show_error: bool = True) -> bool:
        """Register the global toggle hotkey with Windows."""
        success = self.RegisterHotKey(
            self._hotkey_id,
            self._get_hotkey_modifiers(hotkey),
            self._get_hotkey_key_code(hotkey),
        )
        if not success:
            if show_error:
                wx.MessageBox(
                    # Translators: Startup error shown when btText cannot claim
                    # its global shortcut. {} is a shortcut such as Ctrl+Alt+T.
                    _(
                        "The global hotkey {} is already in use and could not "
                        "be registered."
                    ).format(hotkey.to_display_string()),
                    # Translators: Title of an error registering a global shortcut.
                    _("Hotkey error"),
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
            return False
        self._registered_hotkey = hotkey
        return True

    @staticmethod
    def _get_hotkey_modifiers(hotkey: Hotkey) -> int:
        """Translate portable modifiers to wxPython flags."""
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
        """Return the virtual-key code used by wxPython."""
        return hotkey.key_code

    def _unregister_hotkey(self):
        """Release the currently registered global hotkey."""
        if self._registered_hotkey is None:
            return
        self.UnregisterHotKey(self._hotkey_id)
        self._registered_hotkey = None

    def _suspend_hotkey(self):
        """Temporarily release the hotkey while the settings dialog records."""
        self._hotkey_suspended = True
        self._unregister_hotkey()

    def _resume_hotkey(self):
        """Re-register a hotkey after temporary suspension."""
        if not self._hotkey_suspended:
            return
        self._hotkey_suspended = False
        if self._registered_hotkey is None:
            self._register_hotkey(self._settings.toggle_window_hotkey)

    def _on_hotkey_layout_timer(self, event: wx.TimerEvent):
        """Re-register the global hotkey after the input layout changes."""
        keyboard_layout = _get_foreground_keyboard_layout()
        if (
            keyboard_layout is None
            or keyboard_layout == self._hotkey_keyboard_layout
        ):
            return
        self._hotkey_keyboard_layout = keyboard_layout
        _activate_keyboard_layout(keyboard_layout)
        if self._hotkey_suspended or self._registered_hotkey is None:
            return
        hotkey = self._registered_hotkey
        self._unregister_hotkey()
        self._register_hotkey(hotkey)

    def _change_settings(
        self,
        hotkey: Hotkey,
        language: str,
        include_copied_text_in_clipboard_history: bool,
        allow_copied_text_cloud_upload: bool,
        hotstrings_enabled: bool,
        preserve_hotstring_boundary: bool,
        notify_hotstring_expansion: bool,
    ) -> bool:
        """Apply and persist settings, rolling the hotkey back on failure."""
        # Register before saving so an unusable shortcut is never persisted.
        # Every failure path attempts to restore the previous binding.
        old_hotkey = self._settings.toggle_window_hotkey
        hotkey_changed = hotkey != old_hotkey
        hotstrings_were_enabled = self._settings.hotstrings_enabled
        hotstrings_started = False
        if hotstrings_enabled and not hotstrings_were_enabled:
            try:
                self._hotstring_hook.start()
                hotstrings_started = True
            except OSError as error:
                wx.MessageBox(
                    str(error),
                    # Translators: Title for a failure to monitor or expand a
                    # globally typed snippet hotstring.
                    _("Hotstring error"),
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
                return False
        if hotkey_changed:
            self._unregister_hotkey()
        if hotkey_changed and not self._register_hotkey(
            hotkey,
            show_error=False,
        ):
            restored = self._register_hotkey(old_hotkey, show_error=False)
            if restored:
                # Translators: Settings error: the requested global shortcut is
                # occupied, so btText kept the old one. {} is such as Ctrl+Alt+T.
                message = _(
                    "The selected hotkey {} is already in use. "
                    "The previous hotkey has been restored."
                ).format(hotkey.to_display_string())
            else:
                # Translators: Settings error: the requested shortcut is occupied
                # and restoring the old one also failed. {} is such as Ctrl+Alt+T.
                message = _(
                    "The selected hotkey {} is already in use and the previous "
                    "hotkey could not be restored. No global hotkey is active."
                ).format(hotkey.to_display_string())
            wx.MessageBox(
                message,
                # Translators: Title of an error changing the global shortcut.
                _("Hotkey error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            if hotstrings_started:
                self._hotstring_hook.stop()
            return False

        new_settings = AppSettings(
            toggle_window_hotkey=hotkey,
            language=language,
            include_copied_text_in_clipboard_history=(
                include_copied_text_in_clipboard_history
            ),
            allow_copied_text_cloud_upload=allow_copied_text_cloud_upload,
            hotstrings_enabled=hotstrings_enabled,
            preserve_hotstring_boundary=preserve_hotstring_boundary,
            notify_hotstring_expansion=notify_hotstring_expansion,
        )
        try:
            self._settings_store.save(new_settings)
        except SettingsError as error:
            if hotstrings_started:
                self._hotstring_hook.stop()
            if hotkey_changed:
                self._unregister_hotkey()
            restored = (
                not hotkey_changed
                or self._register_hotkey(old_hotkey, show_error=False)
            )
            if hotkey_changed and not restored:
                wx.MessageBox(
                    # Translators: Error after cancelling settings when btText
                    # could not restore the previously active global shortcut.
                    _(
                        "The previous hotkey could not be restored. No global "
                        "hotkey is active."
                    ),
                    # Translators: Title of an error restoring a global shortcut.
                    _("Hotkey error"),
                    wx.OK | wx.ICON_ERROR,
                    self,
                )
            wx.MessageBox(
                format_user_error(error),
                # Translators: Title of an error saving or applying settings.
                _("Settings error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return False
        self._settings = new_settings
        if not hotstrings_enabled:
            self._hotstring_hook.stop()
        return True

    def _refresh_hotstrings(self, *_arguments):
        """Reload active hotstrings after any snippet mutation."""
        self._hotstring_hook.update(self._model.get_hotstring_snippets())

    def _queue_hotstring_expansion(
        self, snippet: datamodel.Snippet, boundary_key: int
    ) -> bool:
        """Queue expansion only when the foreground window is external."""
        target_window = clipboard_paste.get_foreground_window()
        if not clipboard_paste.is_external_window(target_window):
            return False
        wx.CallAfter(
            self._expand_hotstring,
            target_window,
            snippet,
            boundary_key,
        )
        return True

    def _expand_hotstring(
        self,
        target_window: int,
        snippet: datamodel.Snippet,
        boundary_key: int,
    ):
        """Replace a recognized hotstring through the clipboard paste path."""
        try:
            pending = clipboard_paste.expand_hotstring(
                target_window,
                snippet.content,
                len(snippet.hotstring or ""),
                (
                    boundary_key
                    if self._settings.preserve_hotstring_boundary
                    else None
                ),
            )
        except clipboard_paste.PasteError as error:
            wx.MessageBox(
                str(error),
                # Translators: Title for a failure to monitor or expand a
                # globally typed snippet hotstring.
                _("Hotstring error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        wx.CallLater(
            CLIPBOARD_RESTORE_DELAY_MS,
            self._restore_clipboard,
            pending,
            3,
        )
        if self._settings.notify_hotstring_expansion:
            self.tray_icon.show_hotstring_notification(snippet)

    def on_global_hotkey(self, event):
        """Toggle main-window visibility in response to the global shortcut."""
        if self.IsShown():
            self._remember_focused_control()
            self.Hide()
        else:
            self._remember_foreground_window()
            self.show_and_focus()

    def show_and_focus(self):
        """Restore the frame and return focus to a useful child control."""
        self.Show()
        self.Iconize(False)
        self.Raise()
        target = self._last_focused_control or self.category_tree
        target.SetFocus()
        # Repeat after pending native events when restoring a hidden frame.
        wx.CallAfter(target.SetFocus)

    def _remember_focused_control(self):
        """Remember which primary list should regain keyboard focus."""
        focused_control = wx.Window.FindFocus()
        if focused_control in (self.category_tree, self.snippet_list):
            self._last_focused_control = focused_control

    def on_activate(self, event: wx.ActivateEvent):
        """Track focus and the external paste target when deactivated."""
        event.Skip()
        if not event.GetActive():
            self._remember_focused_control()
            wx.CallAfter(self._remember_foreground_window)

    def _remember_foreground_window(self):
        """Remember a valid external foreground window as the paste target."""
        foreground_window = clipboard_paste.get_foreground_window()
        if clipboard_paste.is_external_window(foreground_window):
            self._paste_target_window = foreground_window

    def insert_snippet(self, snippet_id: int):
        """Hide the frame and schedule insertion into the previous window."""
        if self._paste_target_window is None:
            wx.MessageBox(
                # Translators: Error when no previously active external window is
                # available as the destination for inserting a snippet.
                _("There is no previous window to insert the snippet into."),
                # Translators: Title of an error inserting a snippet externally.
                _("Paste error"),
                wx.OK | wx.ICON_ERROR,
                self,
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
                self,
            )
            return

        self._remember_focused_control()
        # Hiding lets Windows reactivate the external target before Ctrl+V.
        self.Hide()
        wx.CallLater(50, self._paste_after_hide, snippet.content)

    def _paste_after_hide(self, text: str):
        """Paste after native window activation has settled."""
        try:
            pending = clipboard_paste.paste_text(self._paste_target_window, text)
        except clipboard_paste.PasteError as error:
            self.Show()
            self.Iconize(False)
            wx.MessageBox(
                str(error),
                # Translators: Title of an error inserting a snippet externally.
                _("Paste error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
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
        """Restore the saved clipboard, retrying transient access failures."""
        # Clipboard access is transiently exclusive, so retry briefly while
        # retaining ownership of the saved snapshot.
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
                wx.OK | wx.ICON_ERROR,
                self,
            )

    def _create_menubar(self):
        """Create application menus and bind their commands."""
        menubar = wx.MenuBar()
        file_menu = wx.Menu()
        # Translators: File-menu command that hides the main window while
        # keeping btText available in the notification area.
        close_item = file_menu.Append(wx.ID_CLOSE, _("&Close"))
        self.Bind(wx.EVT_MENU, self.on_hide_window, close_item)
        file_menu.AppendSeparator()
        # Translators: File-menu command that exits btText completely,
        # including its notification-area icon.
        exit_item = file_menu.Append(wx.ID_EXIT, _("E&xit"))
        self.Bind(wx.EVT_MENU, self.on_exit_application, exit_item)
        # Translators: Main-window menu containing window-close and full-exit
        # commands. "&" marks the keyboard mnemonic.
        menubar.Append(file_menu, _("&File"))
        edit_menu = wx.Menu()
        edit_menu.Append(
            int(self._search_command_id),
            # Translators: Edit-menu command that opens the snippet search
            # dialog. "&" marks the mnemonic; keep F3 after "\t".
            _("&Search...\tF3"),
        )
        edit_menu.AppendSeparator()
        edit_menu.Append(
            int(self._settings_command_id),
            # Translators: Edit-menu command that opens the settings dialog.
            # "&" marks the mnemonic; keep Ctrl+, after "\t".
            _("&Settings...\tCtrl+,"),
        )
        # Translators: Main-window menu containing search and settings commands.
        # "&" marks the keyboard mnemonic.
        menubar.Append(edit_menu, _("&Edit"))
        help_menu = wx.Menu()
        # Translators: Help-menu command that opens application information.
        about_item = help_menu.Append(wx.ID_ABOUT, _("About"))
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        # Translators: Main-window menu containing application information.
        # "&" marks the keyboard mnemonic.
        menubar.Append(help_menu, _("&Help"))
        self.SetMenuBar(menubar)

    def on_hide_window(self, event: wx.CommandEvent):
        """Hide the main window while keeping the application running."""
        self.Close()

    def on_exit_application(self, event: wx.CommandEvent):
        """Request a complete application shutdown."""
        self.allow_close = True
        self.Close()

    def on_settings(self, event: wx.CommandEvent):
        """Open the settings dialog."""
        locale_directory = self._settings_store.locale_directory
        available_languages = (
            i18n.get_available_languages(locale_directory)
            if locale_directory is not None
            else (i18n.DEFAULT_LANGUAGE,)
        )
        with utils.managed_dialog(
            SettingsDialog(
                self,
                self._settings.toggle_window_hotkey,
                self._settings.language,
                self._settings.include_copied_text_in_clipboard_history,
                self._settings.allow_copied_text_cloud_upload,
                self._settings.hotstrings_enabled,
                self._settings.preserve_hotstring_boundary,
                self._settings.notify_hotstring_expansion,
                available_languages,
                self._change_settings,
                self._suspend_hotkey,
                self._resume_hotkey,
            )
        ) as dialog:
            dialog.ShowModal()

    def _create_statusbar(self):
        """Create the status bar used by cross-view notifications."""
        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetStatusText(
            # Translators: Main-window status-bar hint. F3 opens search; Enter
            # inserts the selected snippet. Keep both key names recognizable.
            _("F3: Search snippets    Enter: Insert selected snippet")
        )

    def set_status_text(self, message: str):
        """Display a transient application status message."""
        self.status_bar.SetStatusText(message)

    def on_about(self, event: wx.CommandEvent):
        """Show application name, version, and author."""
        about_info = wx.adv.AboutDialogInfo()
        about_info.AddDeveloper(info.author)
        about_info.SetName(info.name)
        about_info.SetVersion(info.version)
        wx.adv.AboutBox(about_info)

    def _create_tray_icon(self):
        """Create the tray icon and convert window close into hiding."""
        self.allow_close = False
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.tray_icon = TrayIcon(self)

    def on_close(self, event: wx.CloseEvent):
        """Hide normally, or release resources during an explicit exit."""
        if self.allow_close:
            self._hotkey_layout_timer.Stop()
            self._unregister_hotkey()
            self._hotstring_hook.stop()
            self.tray_icon.RemoveIcon()
            self.tray_icon.Destroy()
            event.Skip()
        else:
            self.Hide()
            event.Veto()
