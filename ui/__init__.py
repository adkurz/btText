import wx
import wx.lib.sized_controls as sc
import wx.adv
import pymitter

import app_paths
import datamodel
import info
from ui.snippet_editor import SnippetEditor
from ui.search_dialog import SearchDialog
from ui import utils

CONTENT_PREVIEW_LENGTH = 40


class MainFrame(sc.SizedFrame):
    def __init__(self, ee: pymitter.EventEmitter, model: datamodel.DataModel):
        super().__init__(None, title=wx.GetApp().GetAppName())
        self._ee = ee
        self._model = model
        self.pane = self.GetContentsPane()
        self.pane.SetSizerType("horizontal")
        self.category_list_label = wx.StaticText(self.pane, label="&Categories")
        self.category_list = _CategoryList(self.pane, ee, model)
        self.category_list.SetSizerProps(expand=True, proportion=1) # type: ignore
        self.snippet_list_label = wx.StaticText(self.pane, label="&Snippets")
        self.snippet_list = _SnippetList(self.pane, ee, model)
        self.snippet_list.SetSizerProps(expand=True, proportion=1) # type: ignore
        self.search_button = wx.Button(self.pane, label="&Search... (F3)")
        self.search_button.Bind(wx.EVT_BUTTON, self.on_search)
        self._search_command_id = wx.NewIdRef()
        self.SetAcceleratorTable(
            wx.AcceleratorTable(
                [
                    (
                        wx.ACCEL_NORMAL,
                        wx.WXK_F3,
                        int(self._search_command_id),
                    )
                ]
            )
        )
        self.Bind(
            wx.EVT_MENU,
            self.on_search,
            id=int(self._search_command_id),
        )
        self._create_menubar()
        self._create_statusbar()
        self._create_tray_icon()
        self._register_hotkey()

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

    def _register_hotkey(self):
        """Register Ctrl+Shift+Alt+T as a global hotkey to toggle window visibility."""
        self._hotkey_id = 1
        success = self.RegisterHotKey(
            self._hotkey_id,
            wx.MOD_CONTROL | wx.MOD_SHIFT | wx.MOD_ALT,
            ord('T')
        )
        if not success:
            wx.MessageBox(
                "The global hotkey Ctrl+Shift+Alt+T is already in use by another application and could not be registered.",
                "Hotkey Error",
                wx.OK | wx.ICON_ERROR,
            )
            return
        self.Bind(wx.EVT_HOTKEY, self.on_global_hotkey, id=self._hotkey_id)

    def on_global_hotkey(self, event):
        """Toggle window visibility when the global hotkey is pressed."""
        if self.IsShown():
            self.Hide()
        else:
            self.Show()
            self.Iconize(False)

    def _create_menubar(self):
        menubar = wx.MenuBar()
        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "About")
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        menubar.Append(help_menu, "&Help")
        self.SetMenuBar(menubar)

    def _create_statusbar(self):
        self.status_bar = self.CreateStatusBar()

    def on_about(self, event: wx.CommandEvent):
        about_info = wx.adv.AboutDialogInfo()
        about_info.AddDeveloper(info.author)
        about_info.SetName(info.name)
        about_info.SetVersion(info.version)
        wx.adv.AboutBox(about_info)

    def _create_tray_icon(self):
        self.allow_close = False # Minimize to Tray if closed
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.tray_icon = TrayIcon(self)

    def on_close(self, event: wx.CloseEvent):
        if self.allow_close:
            self.UnregisterHotKey(self._hotkey_id)
            self.tray_icon.RemoveIcon()
            self.tray_icon.Destroy()
            event.Skip()
        else:
            self.Hide()
            event.Veto()


class BaseList(wx.ListView):
    def __init__(self, parent, ee: pymitter.EventEmitter, model: datamodel.DataModel):
        super().__init__(
            parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_SORT_ASCENDING
        )
        self._ee = ee
        self._model = model

    def get_selected_id(self):
        index = self.GetFirstSelected()
        return self.GetItemData(index) if index != wx.NOT_FOUND else None

    def focus_id(self, id: int, select: bool = True):
        index = self.FindItem(-1, id)
        if index == wx.NOT_FOUND:
            return False
        self.Focus(index)
        if select:
            self.Select(index)
        return True

    def sort(self):
        self.SortItems(self._sort_compare)

    def _sort_compare(self, item1: int, item2: int):
        name1: str = self.GetItemText(self.FindItem(-1, item1))
        name2: str = self.GetItemText(self.FindItem(-1, item2))
        # Ignore case:
        name1 = name1.casefold()
        name2 = name2.casefold()
        # Sort
        return (name1 > name2) - (name1 < name2)


class _CategoryList(BaseList):
    def __init__(self, parent, ee: pymitter.EventEmitter, model: datamodel.DataModel):
        super().__init__(parent, ee, model)
        self.AppendColumn("Name")
        # Bind wx events:
        self.Bind(wx.EVT_CONTEXT_MENU, self.context_menu)
        self.Bind(wx.EVT_CHAR, self.key_handler)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.selection_changed)
        # Register events:
        ee.on("category.added", self.add_category_in_list)
        ee.on("category.edited", self.edit_category_in_list)
        ee.on("category.deleted", self.delete_category_from_list)
        # Fill list with categories
        self.update()

    def update(self):
        selected_index = self.get_selected_id()
        self.Freeze()
        self.DeleteAllItems()
        for c in self._model.get_categories(True):
            index = self.Append((c.name,))
            self.SetItemData(index, c.id or 0)
        self.sort()
        if selected_index is not None:
            self.focus_id(selected_index)
        self.Thaw()

    def selection_changed(self, event: wx.ListEvent):
        id = self.get_selected_id()
        self._ee.emit("category_list.changed", id)

    def context_menu(self, event: wx.ContextMenuEvent):
        menu = wx.Menu()
        new_category = menu.Append(wx.ID_ANY, "New Category")
        menu.Bind(wx.EVT_MENU, self.add_category, new_category)
        category_id = self.get_selected_id()
        if category_id is not None:
            edit_category = menu.Append(wx.ID_ANY, "Edit")
            menu.Bind(wx.EVT_MENU, self.edit_category, edit_category)
            delete_category = menu.Append(wx.ID_ANY, "Delete")
            menu.Bind(wx.EVT_MENU, self.delete_category, delete_category)
        self.PopupMenu(menu)

    def key_handler(self, event: wx.KeyEvent):
        key = event.GetKeyCode()
        if key == wx.WXK_CONTROL_N:
            self.add_category(event)
        elif key == wx.WXK_F2:
            self.edit_category(event)
        elif key == wx.WXK_DELETE:
            self.delete_category(event)
        else:
            event.Skip()

    def add_category(self, event: wx.CommandEvent | wx.KeyEvent):
        with utils.managed_dialog(
            wx.TextEntryDialog(
                self, "Enter the name of the new category", "Add Category"
            )
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            value = dlg.GetValue()
        if not value:
            wx.MessageBox(
                "The name of the category must not be empty.",
                "Error",
                style=wx.OK | wx.ICON_ERROR,
            )
            return

        try:
            category = datamodel.Category(name=value)
            id = self._model.add_category(category)
        except datamodel.CategoryValidationError as e:
            wx.MessageBox(
                str(e), "Error", style=wx.OK | wx.ICON_ERROR
            )

    def add_category_in_list(self, category: datamodel.Category):
        self.Freeze()
        category_index = self.Append(
            (
                category.name,
            )
        )
        self.SetItemData(category_index, category.id or 0)
        self.Focus(category_index)
        self.sort()
        self.Thaw()

    def edit_category(self, event: wx.CommandEvent | wx.KeyEvent):
        category_id = self.get_selected_id()
        if category_id is None:
            return # No category
        try:
            category = self._model.get_category(category_id)
        except datamodel.EntityNotFoundError as e:
            wx.MessageBox(str(e), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update()
            return
        with utils.managed_dialog(
            wx.TextEntryDialog(
                self,
                "Enter the new name of the category",
                "Edit Category",
                value=category.name,
            )
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            category.name = dlg.GetValue()
        if not category.name:
            wx.MessageBox(
                "The name of the category must not be empty.",
                "Error",
                style=wx.OK | wx.ICON_ERROR,
            )
            return
        try:
            self._model.edit_category(category)
        except datamodel.DataModelError as e:
            wx.MessageBox(
                str(e),
                "Error",
                style=wx.OK | wx.ICON_ERROR,
            )

    def edit_category_in_list(self, category: datamodel.Category):
        self.Freeze()
        category_index = self.FindItem(-1, category.id)
        self.SetItem(category_index, 0, category.name)
        self.sort()
        self.Thaw()

    def delete_category(self, event: wx.CommandEvent | wx.KeyEvent):
        id = self.get_selected_id()
        if id is None:
            return
        try:
            category = self._model.get_category(id)
        except datamodel.EntityNotFoundError as e:
            wx.MessageBox(str(e), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update()
            return
        with utils.managed_dialog(
            wx.MessageDialog(
                self,
                "Do you want to delete the category {}".format(category.name),
                "Delete category?",
                style=wx.YES_NO | wx.ICON_QUESTION,
            )
        ) as dlg:
            if dlg.ShowModal() != wx.ID_YES:
                return
        try:
            self._model.delete_category(id)
        except datamodel.DataModelError as e:
            wx.MessageBox(str(e), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update()

    def delete_category_from_list(self, id):
        category_index = self.FindItem(-1, id)
        self.DeleteItem(category_index)


class _SnippetList(BaseList):
    def __init__(self, parent, ee: pymitter.EventEmitter, model: datamodel.DataModel):
        super().__init__(parent, ee, model)
        self.selected_category_id = None
        self.AppendColumn("Name")
        self.AppendColumn("Weight")
        weight_number = self.AppendColumn("Weight_number")
        self.SetColumnWidth(weight_number, 0)
        self.AppendColumn("Content preview")
        # Bind wx events:
        self.Bind(wx.EVT_CONTEXT_MENU, self.context_menu)
        self.Bind(wx.EVT_CHAR, self.key_handler)
        # Register events:
        ee.on("category_list.changed", self.update)
        ee.on("category.deleted", self.category_deleted)
        ee.on('snippet.added', self.add_snippet_in_list)
        ee.on('snippet.edited', self.edit_snippet_in_list)
        ee.on('snippet.deleted', self.delete_snippet_from_list)

    def category_deleted(self, category_id: int):
        if category_id == self.selected_category_id:
            self.update(None, force=True)

    def update(self, category_id: int, force: bool = False):
        if category_id == self.selected_category_id and not force:
            return # Nothing changed
        self.selected_category_id = category_id
        self.Freeze()
        self.DeleteAllItems()
        if category_id is None:
            self.Thaw()
            return
        for s in self._model.get_snippets(category_id):
            index = self.Append((s.name, utils.get_weight_string(s.weight), s.weight, utils.reduce_string(s.content, CONTENT_PREVIEW_LENGTH)))
            self.SetItemData(index, s.id or 0)
        self.sort()
        self.Thaw()

    def context_menu(self, event: wx.ContextMenuEvent):
        menu = wx.Menu()
        new_snippet = menu.Append(wx.ID_ANY, "New Snippet")
        menu.Bind(wx.EVT_MENU, self.add_snippet, new_snippet)
        if self.get_selected_id() is not None:
            edit_snippet = menu.Append(wx.ID_ANY, "Edit Snippet")
            menu.Bind(wx.EVT_MENU, self.edit_snippet, edit_snippet)
        self.PopupMenu(menu)

    def key_handler(self, event: wx.KeyEvent):
        key = event.GetKeyCode()
        if key == wx.WXK_CONTROL_N:
            self.add_snippet(event)
        elif key == wx.WXK_F2:
            self.edit_snippet(event)
        elif key == wx.WXK_DELETE:
            self.delete_snippet(event)
        else:
            event.Skip()

    def add_snippet(self, event: wx.CommandEvent | wx.KeyEvent):
        if self.selected_category_id is None:
            return # No Category
        with utils.managed_dialog(
            SnippetEditor(
                self.GetGrandParent(),
                self._ee,
                self._model,
                self.selected_category_id,
            )
        ) as editor:
            editor.ShowModal()

    def edit_snippet(self, event: wx.CommandEvent | wx.KeyEvent):
        id = self.get_selected_id()
        if id is None or self.selected_category_id is None:
            return
        try:
            snippet = self._model.get_snippet(id)
        except datamodel.EntityNotFoundError as e:
            wx.MessageBox(str(e), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update(self.selected_category_id, force=True)
            return
        with utils.managed_dialog(
            SnippetEditor(
                self.GetGrandParent(),
                self._ee,
                self._model,
                self.selected_category_id,
                snippet,
            )
        ) as editor:
            editor.ShowModal()

    def delete_snippet(self, event: wx.CommandEvent | wx.KeyEvent):
        id = self.get_selected_id()
        if id is None:
            return
        try:
            snippet = self._model.get_snippet(id)
        except datamodel.EntityNotFoundError as e:
            wx.MessageBox(str(e), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update(self.selected_category_id, force=True)
            return
        with utils.managed_dialog(
            wx.MessageDialog(
                self,
                "Do you want to delete the snippet {}".format(snippet.name),
                "Delete snippet?",
                style=wx.YES_NO | wx.ICON_QUESTION,
            )
        ) as dlg:
            if dlg.ShowModal() != wx.ID_YES:
                return
        try:
            self._model.delete_snippet(id)
        except datamodel.DataModelError as e:
            wx.MessageBox(str(e), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update(self.selected_category_id, force=True)

    def delete_snippet_from_list(self, snippet: datamodel.Snippet):
        index = self.FindItem(-1, snippet.id)
        if index == wx.NOT_FOUND:
            return
        self.DeleteItem(index)

    def add_snippet_in_list(self, snippet: datamodel.Snippet):
        # If the category of the snippet is not the shown category, don't add it:
        if snippet.category_id != self.selected_category_id:
            return
        # Add snippet into list:
        self.Freeze()
        snippet_index = self.Append((snippet.name, utils.get_weight_string(snippet.weight), snippet.weight, utils.reduce_string(snippet.content, CONTENT_PREVIEW_LENGTH)))
        self.SetItemData(snippet_index, snippet.id or 0)
        self.Focus(snippet_index)
        self.Select(snippet_index)
        self.sort()
        self.Thaw()

    def edit_snippet_in_list(self, snippet: datamodel.Snippet):
        # If the snippet has changed category, remove it from current list:
        if snippet.category_id != self.selected_category_id:
            self.delete_snippet_from_list(snippet)
            return
        # Update snippet in list:
        if snippet.id is None:
            return
        index = self.FindItem(-1, snippet.id)
        if index == wx.NOT_FOUND:
            return
        self.Freeze()
        self.SetItem(index, 0, snippet.name)
        self.SetItem(index, 1, utils.get_weight_string(snippet.weight))
        self.SetItem(index, 2, str(snippet.weight))
        self.SetItem(index, 3, utils.reduce_string(snippet.content, CONTENT_PREVIEW_LENGTH))
        self.sort()
        self.Thaw()

    def _sort_compare(self, item1, item2):
        weight1 = int(self.GetItemText(self.FindItem(-1, item1), 2))
        weight2 = int(self.GetItemText(self.FindItem(-1, item2), 2))
        # Sort by weight descending first
        weight_result = (weight1 < weight2) - (weight1 > weight2)
        if weight_result != 0:
            return weight_result
        else:
            return super()._sort_compare(item1, item2)


class TrayIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame: MainFrame):
        super().__init__()
        self._frame = frame
        icon = wx.Icon(wx.Bitmap(str(app_paths.get_icon_file())))
        self.SetIcon(icon, "{app_name} - {app_version}".format(app_name=info.name, app_version=info.version)) # type: ignore
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_left_click)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        restore = menu.Append(wx.ID_ANY, "Show snippets")
        self.Bind(wx.EVT_MENU, self.on_restore, restore)
        exit = menu.Append(wx.ID_EXIT, "Exit")
        self.Bind(wx.EVT_MENU, self.on_exit, exit)
        return menu

    def on_left_click(self, event: wx.Event):
        self.on_restore(event)

    def on_restore(self, event: wx.Event):
        self._frame.Show()
        self._frame.Iconize(False)

    def on_exit(self, event):
        self._frame.allow_close = True
        self._frame.Close()
