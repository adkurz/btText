"""Main-window coordination for navigation, hotkeys, and external paste."""

import pymitter
import wx
import wx.adv
import wx.lib.sized_controls as sc

from core import datamodel
import i18n
import info
from core.app_settings import AppSettings, SettingsStore
from core.error_messages import format_user_error
from i18n import _
from ui import utils
from ui.category_tree import CategoryTree
from ui.database_selection import select_database
from ui.global_hotkey import WxGlobalHotkeyBinding
from ui.hotstring_controller import HotstringController
from ui.paste_controller import PasteController
from ui.search_dialog import SearchDialog
from ui.settings_controller import SettingsController
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
        self._create_process_integrations(
            ee,
            model,
            settings_store,
            settings,
        )
        self._bind_application_events()
        self._create_primary_views(ee, model)
        self._bind_application_commands()
        self._create_menubar()
        self._create_statusbar()
        self._create_tray_icon()
        self._configure_frame_geometry()
        # Let wx finish creating and displaying the frame before touching
        # process-wide hooks or loading all hotstrings from the database.
        wx.CallAfter(self._start_process_integrations)

    def _create_process_integrations(
        self,
        ee: pymitter.EventEmitter,
        model: datamodel.DataModel,
        settings_store: SettingsStore,
        settings: AppSettings,
    ) -> None:
        """Create controllers for process-wide operating-system features."""
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
            lambda: self._settings_controller.settings,
            self._paste_controller.schedule_restore,
            lambda snippet: self.tray_icon.show_hotstring_notification(
                snippet
            ),
        )
        self._settings_controller = SettingsController(
            self,
            settings_store,
            settings,
            self._global_hotkey,
            self._hotstring_controller,
        )

    def _bind_application_events(self) -> None:
        """Bind cross-view and process-wide application events."""
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

    def _create_primary_views(
        self,
        ee: pymitter.EventEmitter,
        model: datamodel.DataModel,
    ) -> None:
        """Create and lay out the category and snippet views."""
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
            lambda: (
                self._settings_controller.settings
                .include_copied_text_in_clipboard_history
            ),
            lambda: (
                self._settings_controller.settings
                .allow_copied_text_cloud_upload
            ),
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

    def _bind_application_commands(self) -> None:
        """Create command identifiers and bind their menu handlers."""
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

    def _start_process_integrations(self) -> None:
        """Activate configured hotkeys and hotstring monitoring."""
        self._settings_controller.register_initial_hotkey()
        self._hotstring_controller.refresh()
        if self._settings_controller.settings.hotstrings_enabled:
            self._hotstring_controller.start()

    def _configure_frame_geometry(self) -> None:
        """Apply initial frame size constraints and screen placement."""
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

    def _on_hotkey_layout_timer(self, event: wx.TimerEvent):
        """Re-register the global hotkey after the input layout changes."""
        failed_hotkey = self._global_hotkey.refresh_keyboard_layout()
        if failed_hotkey is not None:
            self._settings_controller.show_hotkey_registration_error(
                failed_hotkey
            )

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

        if not self._settings_controller.save_database_file(
            str(selection.path)
        ):
            return
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
        settings = self._settings_controller.settings
        available_languages = (
            i18n.get_available_languages(locale_directory)
            if locale_directory is not None
            else (i18n.DEFAULT_LANGUAGE,)
        )
        with utils.managed_dialog(
            SettingsDialog(
                self,
                settings.toggle_window_hotkey,
                settings.language,
                settings.include_copied_text_in_clipboard_history,
                settings.allow_copied_text_cloud_upload,
                settings.hotstrings_enabled,
                settings.preserve_hotstring_boundary,
                settings.notify_hotstring_expansion,
                available_languages,
                self._settings_controller.apply,
                self._settings_controller.suspend_hotkey,
                self._settings_controller.resume_hotkey,
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
            self._settings_controller.unregister_hotkey()
            self._hotstring_controller.stop()
            self.tray_icon.RemoveIcon()
            self.tray_icon.Destroy()
            event.Skip()
        else:
            self.Hide()
            event.Veto()
