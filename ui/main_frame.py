"""Main-window coordination for navigation, hotkeys, and external paste."""

import dataclasses

import pymitter
import wx
import wx.adv
import wx.lib.sized_controls as sc

from core import datamodel
import i18n
import info
from core.app_settings import AppSettings, SettingsError, SettingsStore
from core.error_messages import format_user_error
from core.shortcuts import Hotkey
from i18n import _
from ui import utils
from ui.category_tree import CategoryTree
from ui.database_selection import select_database
from ui.global_hotkey import WxGlobalHotkeyBinding
from ui.hotstring_controller import HotstringController
from ui.paste_controller import PasteController
from ui.search_dialog import SearchDialog
from ui.shortcut_display import format_hotkey
from ui.settings_dialog import SettingsDialog
from ui.snippet_list import SnippetList
from ui.tray_icon import TrayIcon
from ui.transfer import TransferBuffer

HOTKEY_LAYOUT_CHECK_INTERVAL_MS = 500

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
        self._global_hotkey = WxGlobalHotkeyBinding(self, hotkey_id=1)
        self._hotkey_layout_timer = wx.Timer(self)
        self.Bind(
            wx.EVT_TIMER,
            self._on_hotkey_layout_timer,
            self._hotkey_layout_timer,
        )
        self._hotkey_layout_timer.Start(HOTKEY_LAYOUT_CHECK_INTERVAL_MS)
        self._paste_controller = PasteController(
            self,
            model,
            self._prepare_external_paste,
            self._reveal_after_paste_error,
        )
        self._hotstring_controller = HotstringController(
            self,
            ee,
            model,
            lambda: self._settings,
            self._paste_controller.schedule_restore,
            lambda snippet: self.tray_icon.show_hotstring_notification(
                snippet
            ),
        )
        self._ee.on(
            "snippet.insert_requested",
            self._paste_controller.insert_snippet,
        )
        self._ee.on("status.changed", self.set_status_text)
        self.Bind(wx.EVT_ACTIVATE, self.on_activate)
        self.Bind(
            wx.EVT_HOTKEY,
            self.on_global_hotkey,
            id=self._global_hotkey.hotkey_id,
        )
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
        self._database_command_id = wx.NewIdRef()
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
        self.Bind(
            wx.EVT_MENU,
            self.on_select_database,
            id=int(self._database_command_id),
        )
        self._create_menubar()
        self._create_statusbar()
        self._create_tray_icon()
        self._register_hotkey(self._settings.toggle_window_hotkey)
        self._hotstring_controller.refresh()
        if self._settings.hotstrings_enabled:
            self._hotstring_controller.start()
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
        success = self._global_hotkey.register(hotkey)
        if not success and show_error:
            self._show_hotkey_registration_error(hotkey)
        return success

    def _unregister_hotkey(self):
        """Release the currently registered global hotkey."""
        self._global_hotkey.unregister()

    def _suspend_hotkey(self):
        """Temporarily release the hotkey while the settings dialog records."""
        self._global_hotkey.suspend()

    def _resume_hotkey(self):
        """Re-register a hotkey after temporary suspension."""
        hotkey = self._settings.toggle_window_hotkey
        if not self._global_hotkey.resume(hotkey):
            self._show_hotkey_registration_error(hotkey)

    def _on_hotkey_layout_timer(self, event: wx.TimerEvent):
        """Re-register the global hotkey after the input layout changes."""
        failed_hotkey = self._global_hotkey.refresh_keyboard_layout()
        if failed_hotkey is not None:
            self._show_hotkey_registration_error(failed_hotkey)

    def _show_hotkey_registration_error(self, hotkey: Hotkey) -> None:
        """Show the standard error for a global hotkey registration failure."""
        wx.MessageBox(
            # Translators: Startup error shown when btText cannot claim its
            # global shortcut. {} is a shortcut such as Ctrl+Alt+T.
            _(
                "The global hotkey {} is already in use and could not "
                "be registered."
            ).format(format_hotkey(hotkey)),
            # Translators: Title of an error registering a global shortcut.
            _("Hotkey error"),
            wx.OK | wx.ICON_ERROR,
            self,
        )

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
            if not self._hotstring_controller.start():
                return False
            hotstrings_started = True
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
                ).format(format_hotkey(hotkey))
            else:
                # Translators: Settings error: the requested shortcut is occupied
                # and restoring the old one also failed. {} is such as Ctrl+Alt+T.
                message = _(
                    "The selected hotkey {} is already in use and the previous "
                    "hotkey could not be restored. No global hotkey is active."
                ).format(format_hotkey(hotkey))
            wx.MessageBox(
                message,
                # Translators: Title of an error changing the global shortcut.
                _("Hotkey error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            if hotstrings_started:
                self._hotstring_controller.stop()
            return False

        new_settings = AppSettings(
            database_file=self._settings.database_file,
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
                self._hotstring_controller.stop()
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
            self._hotstring_controller.stop()
        return True

    def on_global_hotkey(self, event):
        """Toggle main-window visibility in response to the global shortcut."""
        if self.IsShown():
            self._remember_focused_control()
            self.Hide()
        else:
            self._paste_controller.remember_foreground_window()
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
            wx.CallAfter(self._paste_controller.remember_foreground_window)

    def _prepare_external_paste(self) -> None:
        """Remember focus and hide while Windows activates the paste target."""
        self._remember_focused_control()
        self.Hide()

    def _reveal_after_paste_error(self) -> None:
        """Reveal the frame again when external paste preparation fails."""
        self.Show()
        self.Iconize(False)

    def _create_menubar(self):
        """Create application menus and bind their commands."""
        menubar = wx.MenuBar()
        file_menu = wx.Menu()
        file_menu.Append(
            int(self._database_command_id),
            # Translators: File-menu command for selecting another snippet
            # database. The selection is used after restarting btText.
            _("Change &database..."),
        )
        file_menu.AppendSeparator()
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

    def on_select_database(self, event: wx.CommandEvent):
        """Validate and remember a database to use after the next start."""
        selection = select_database(self)
        if selection is None:
            return
        candidate = None
        try:
            candidate = datamodel.DataModel(
                pymitter.EventEmitter(),
                selection.path,
                allow_create=selection.create,
            )
        except datamodel.DataModelError as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Title for an error opening a selected snippet
                # database.
                _("Database error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        finally:
            if candidate is not None:
                candidate.close()

        new_settings = dataclasses.replace(
            self._settings,
            database_file=str(selection.path),
        )
        try:
            self._settings_store.save(new_settings)
        except SettingsError as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Title for an error saving the selected database
                # path in the application settings.
                _("Settings error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        self._settings = new_settings
        wx.MessageBox(
            # Translators: Confirmation after choosing the database that btText
            # should open following its next restart.
            _("The selected database will be used the next time btText starts."),
            # Translators: Title confirming that another database was selected.
            _("Database selected"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

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
            self._hotstring_controller.stop()
            self.tray_icon.RemoveIcon()
            self.tray_icon.Destroy()
            event.Skip()
        else:
            self.Hide()
            event.Veto()
