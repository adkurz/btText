import pymitter
import wx

import datamodel
from ui import utils
from ui.base_list import BaseList


class CategoryList(BaseList):
    def __init__(self, parent, ee: pymitter.EventEmitter, model: datamodel.DataModel):
        super().__init__(parent, ee, model)
        self.AppendColumn("Name")
        self.AppendColumn("Snippets")
        self.Bind(wx.EVT_CONTEXT_MENU, self.context_menu)
        self.Bind(wx.EVT_CHAR, self.key_handler)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.selection_changed)
        ee.on("category.added", self.add_category_in_list)
        ee.on("category.edited", self.edit_category_in_list)
        ee.on("category.deleted", self.delete_category_from_list)
        ee.on("snippet.added", self.snippet_count_changed)
        ee.on("snippet.edited", self.snippet_count_changed)
        ee.on("snippet.deleted", self.snippet_count_changed)
        self.update()

    def update(self):
        selected_index = self.get_selected_id()
        self.Freeze()
        self.DeleteAllItems()
        for category in self._model.get_categories(True):
            index = self.Append(
                (category.name, str(category.number_of_snippets))
            )
            self.SetItemData(index, category.id or 0)
        self.sort()
        if selected_index is not None:
            self.focus_id(selected_index)
        self.Thaw()

    def selection_changed(self, event: wx.ListEvent):
        category_id = self.get_selected_id()
        self._ee.emit("category_list.changed", category_id)

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
                self,
                "Enter the name of the new category",
                "Add Category",
            )
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            value = dialog.GetValue()
        if not value:
            wx.MessageBox(
                "The name of the category must not be empty.",
                "Error",
                style=wx.OK | wx.ICON_ERROR,
            )
            return

        try:
            self._model.add_category(datamodel.Category(name=value))
        except datamodel.CategoryValidationError as error:
            wx.MessageBox(str(error), "Error", style=wx.OK | wx.ICON_ERROR)

    def add_category_in_list(self, category: datamodel.Category):
        self.Freeze()
        category_index = self.Append(
            (category.name, str(category.number_of_snippets))
        )
        self.SetItemData(category_index, category.id or 0)
        self.Focus(category_index)
        self.sort()
        self.Thaw()

    def edit_category(self, event: wx.CommandEvent | wx.KeyEvent):
        category_id = self.get_selected_id()
        if category_id is None:
            return
        try:
            category = self._model.get_category(category_id)
        except datamodel.EntityNotFoundError as error:
            wx.MessageBox(str(error), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update()
            return
        with utils.managed_dialog(
            wx.TextEntryDialog(
                self,
                "Enter the new name of the category",
                "Edit Category",
                value=category.name,
            )
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            category.name = dialog.GetValue()
        if not category.name:
            wx.MessageBox(
                "The name of the category must not be empty.",
                "Error",
                style=wx.OK | wx.ICON_ERROR,
            )
            return
        try:
            self._model.edit_category(category)
        except datamodel.DataModelError as error:
            wx.MessageBox(str(error), "Error", style=wx.OK | wx.ICON_ERROR)

    def edit_category_in_list(self, category: datamodel.Category):
        self.Freeze()
        category_index = self.FindItem(-1, category.id)
        self.SetItem(category_index, 0, category.name)
        self.sort()
        self.Thaw()

    def delete_category(self, event: wx.CommandEvent | wx.KeyEvent):
        category_id = self.get_selected_id()
        if category_id is None:
            return
        try:
            category = self._model.get_category(category_id)
        except datamodel.EntityNotFoundError as error:
            wx.MessageBox(str(error), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update()
            return
        with utils.managed_dialog(
            wx.MessageDialog(
                self,
                "Do you want to delete the category {}".format(category.name),
                "Delete category?",
                style=wx.YES_NO | wx.ICON_QUESTION,
            )
        ) as dialog:
            if dialog.ShowModal() != wx.ID_YES:
                return
        try:
            self._model.delete_category(category_id)
        except datamodel.DataModelError as error:
            wx.MessageBox(str(error), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update()

    def delete_category_from_list(self, category_id):
        category_index = self.FindItem(-1, category_id)
        self.DeleteItem(category_index)

    def snippet_count_changed(self, snippet: datamodel.Snippet):
        self.update()
