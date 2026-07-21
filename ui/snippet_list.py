import pymitter
import wx

import datamodel
from ui import utils
from ui.base_list import BaseList
from ui.snippet_editor import SnippetEditor

CONTENT_PREVIEW_LENGTH = 40


class SnippetList(BaseList):
    def __init__(self, parent, ee: pymitter.EventEmitter, model: datamodel.DataModel):
        super().__init__(parent, ee, model)
        self.selected_category_id = None
        self.AppendColumn("Name")
        self.AppendColumn("Weight")
        weight_number = self.AppendColumn("Weight_number")
        self.SetColumnWidth(weight_number, 0)
        self.AppendColumn("Content preview")
        self.Bind(wx.EVT_CONTEXT_MENU, self.context_menu)
        self.Bind(wx.EVT_CHAR, self.key_handler)
        ee.on("category_list.changed", self.update)
        ee.on("category.deleted", self.category_deleted)
        ee.on("snippet.added", self.add_snippet_in_list)
        ee.on("snippet.edited", self.edit_snippet_in_list)
        ee.on("snippet.deleted", self.delete_snippet_from_list)

    def category_deleted(self, category_id: int):
        if category_id == self.selected_category_id:
            self.update(None, force=True)

    def update(self, category_id: int | None, force: bool = False):
        if category_id == self.selected_category_id and not force:
            return
        self.selected_category_id = category_id
        self.Freeze()
        self.DeleteAllItems()
        if category_id is None:
            self.Thaw()
            return
        for snippet in self._model.get_snippets(category_id):
            index = self.Append(
                (
                    snippet.name,
                    utils.get_weight_string(snippet.weight),
                    snippet.weight,
                    utils.reduce_string(
                        snippet.content,
                        CONTENT_PREVIEW_LENGTH,
                    ),
                )
            )
            self.SetItemData(index, snippet.id or 0)
        self.sort()
        self.Thaw()

    def context_menu(self, event: wx.ContextMenuEvent):
        menu = wx.Menu()
        new_snippet = menu.Append(wx.ID_ANY, "New Snippet")
        menu.Bind(wx.EVT_MENU, self.add_snippet, new_snippet)
        if self.get_selected_id() is not None:
            insert_snippet = menu.Append(wx.ID_ANY, "Insert Snippet")
            menu.Bind(wx.EVT_MENU, self.insert_snippet, insert_snippet)
            edit_snippet = menu.Append(wx.ID_ANY, "Edit Snippet")
            menu.Bind(wx.EVT_MENU, self.edit_snippet, edit_snippet)
        self.PopupMenu(menu)

    def key_handler(self, event: wx.KeyEvent):
        key = event.GetKeyCode()
        if key == wx.WXK_CONTROL_N:
            self.add_snippet(event)
        elif key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.insert_snippet(event)
        elif key == wx.WXK_F2:
            self.edit_snippet(event)
        elif key == wx.WXK_DELETE:
            self.delete_snippet(event)
        else:
            event.Skip()

    def insert_snippet(self, event: wx.CommandEvent | wx.KeyEvent):
        snippet_id = self.get_selected_id()
        if snippet_id is not None:
            self._ee.emit("snippet.insert_requested", snippet_id)

    def add_snippet(self, event: wx.CommandEvent | wx.KeyEvent):
        if self.selected_category_id is None:
            return
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
        snippet_id = self.get_selected_id()
        if snippet_id is None or self.selected_category_id is None:
            return
        try:
            snippet = self._model.get_snippet(snippet_id)
        except datamodel.EntityNotFoundError as error:
            wx.MessageBox(str(error), "Error", style=wx.OK | wx.ICON_ERROR)
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
        snippet_id = self.get_selected_id()
        if snippet_id is None:
            return
        try:
            snippet = self._model.get_snippet(snippet_id)
        except datamodel.EntityNotFoundError as error:
            wx.MessageBox(str(error), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update(self.selected_category_id, force=True)
            return
        with utils.managed_dialog(
            wx.MessageDialog(
                self,
                "Do you want to delete the snippet {}".format(snippet.name),
                "Delete snippet?",
                style=wx.YES_NO | wx.ICON_QUESTION,
            )
        ) as dialog:
            if dialog.ShowModal() != wx.ID_YES:
                return
        try:
            self._model.delete_snippet(snippet_id)
        except datamodel.DataModelError as error:
            wx.MessageBox(str(error), "Error", style=wx.OK | wx.ICON_ERROR)
            self.update(self.selected_category_id, force=True)

    def delete_snippet_from_list(self, snippet: datamodel.Snippet):
        index = self.FindItem(-1, snippet.id)
        if index == wx.NOT_FOUND:
            return
        self.DeleteItem(index)

    def add_snippet_in_list(self, snippet: datamodel.Snippet):
        if snippet.category_id != self.selected_category_id:
            return
        self.Freeze()
        snippet_index = self.Append(
            (
                snippet.name,
                utils.get_weight_string(snippet.weight),
                snippet.weight,
                utils.reduce_string(snippet.content, CONTENT_PREVIEW_LENGTH),
            )
        )
        self.SetItemData(snippet_index, snippet.id or 0)
        self.Focus(snippet_index)
        self.Select(snippet_index)
        self.sort()
        self.Thaw()

    def edit_snippet_in_list(self, snippet: datamodel.Snippet):
        if snippet.category_id != self.selected_category_id:
            self.delete_snippet_from_list(snippet)
            return
        if snippet.id is None:
            return
        index = self.FindItem(-1, snippet.id)
        if index == wx.NOT_FOUND:
            return
        self.Freeze()
        self.SetItem(index, 0, snippet.name)
        self.SetItem(index, 1, utils.get_weight_string(snippet.weight))
        self.SetItem(index, 2, str(snippet.weight))
        self.SetItem(
            index,
            3,
            utils.reduce_string(snippet.content, CONTENT_PREVIEW_LENGTH),
        )
        self.sort()
        self.Thaw()

    def _sort_compare(self, item1, item2):
        weight1 = int(self.GetItemText(self.FindItem(-1, item1), 2))
        weight2 = int(self.GetItemText(self.FindItem(-1, item2), 2))
        weight_result = (weight1 < weight2) - (weight1 > weight2)
        if weight_result != 0:
            return weight_result
        return super()._sort_compare(item1, item2)
