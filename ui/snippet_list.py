import pymitter
import wx

import datamodel
from ui import utils
from ui.base_list import BaseList
from ui.snippet_editor import SnippetEditor
from ui.transfer import TransferBuffer

CONTENT_PREVIEW_LENGTH = 40


class SnippetList(BaseList):
    def __init__(
        self,
        parent,
        ee: pymitter.EventEmitter,
        model: datamodel.DataModel,
        transfer_buffer: TransferBuffer,
    ):
        super().__init__(parent, ee, model)
        self._transfer_buffer = transfer_buffer
        self.selected_category_id = None
        self.AppendColumn("Name")
        self.AppendColumn("Weight")
        weight_number = self.AppendColumn("Weight_number")
        self.SetColumnWidth(weight_number, 0)
        self.AppendColumn("Content preview")
        self.Bind(wx.EVT_CONTEXT_MENU, self.context_menu)
        self.Bind(wx.EVT_CHAR, self.key_handler)
        self.Bind(wx.EVT_LIST_BEGIN_DRAG, self.begin_drag)
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
        if self.selected_category_id is not None:
            paste_item = menu.Append(
                wx.ID_PASTE,
                "Paste into category\tCtrl+V",
            )
            menu.Bind(wx.EVT_MENU, self.paste, paste_item)
            paste_root_item = menu.Append(
                wx.ID_ANY,
                "Paste category as top-level\tCtrl+Shift+V",
            )
            menu.Bind(
                wx.EVT_MENU,
                lambda evt: self.paste(evt, as_top_level=True),
                paste_root_item,
            )
        if self.get_selected_id() is not None:
            insert_snippet = menu.Append(wx.ID_ANY, "Insert Snippet")
            menu.Bind(wx.EVT_MENU, self.insert_snippet, insert_snippet)
            edit_snippet = menu.Append(wx.ID_ANY, "Edit Snippet")
            menu.Bind(wx.EVT_MENU, self.edit_snippet, edit_snippet)
            menu.AppendSeparator()
            copy_snippet = menu.Append(wx.ID_COPY, "Copy\tCtrl+C")
            cut_snippet = menu.Append(wx.ID_CUT, "Cut\tCtrl+X")
            menu.Bind(
                wx.EVT_MENU,
                lambda evt: self.copy_or_cut(True),
                copy_snippet,
            )
            menu.Bind(
                wx.EVT_MENU,
                lambda evt: self.copy_or_cut(False),
                cut_snippet,
            )
        self.PopupMenu(menu)

    def key_handler(self, event: wx.KeyEvent):
        key = event.GetKeyCode()
        if event.ControlDown() and key in (ord("C"), 3, ord("X"), 24):
            self.copy_or_cut(key in (ord("C"), 3))
        elif event.ControlDown() and key in (ord("V"), 22):
            self.paste(event, as_top_level=event.ShiftDown())
        elif key == wx.WXK_CONTROL_N:
            self.add_snippet(event)
        elif key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.insert_snippet(event)
        elif key == wx.WXK_F2:
            self.edit_snippet(event)
        elif key == wx.WXK_DELETE:
            self.delete_snippet(event)
        else:
            event.Skip()

    def copy_or_cut(self, copy: bool):
        snippet_id = self.get_selected_id()
        if snippet_id is None:
            return
        self._transfer_buffer.set("snippet", snippet_id, copy)
        action = "Copied" if copy else "Cut"
        self._ee.emit(
            "status.changed",
            "{} snippet. Select a category and press Ctrl+V.".format(action),
        )

    def paste(self, event, as_top_level: bool = False):
        transfer = self._transfer_buffer.value
        category_id = self.selected_category_id
        if transfer is None:
            wx.Bell()
            return
        if as_top_level:
            if transfer.kind != "category":
                wx.MessageBox(
                    "Only a category can be pasted as a top-level category.",
                    "Paste as top-level",
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
                return
            category_id = None
        elif category_id is None:
            wx.Bell()
            return
        try:
            if transfer.kind == "category":
                if transfer.copy:
                    self._model.copy_category(
                        transfer.entity_id,
                        category_id,
                    )
                else:
                    self._model.move_category(
                        transfer.entity_id,
                        category_id,
                    )
            elif transfer.kind == "snippet":
                if transfer.copy:
                    snippet = self._model.copy_snippet(
                        transfer.entity_id,
                        category_id,
                    )
                else:
                    snippet = self._model.move_snippet(
                        transfer.entity_id,
                        category_id,
                    )
                if snippet.id is not None:
                    self.focus_id(snippet.id)
            else:
                return
        except datamodel.DataModelError as error:
            wx.MessageBox(
                str(error),
                "Paste error",
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        if not transfer.copy:
            self._transfer_buffer.clear()
        self._ee.emit("status.changed", "Transfer completed.")

    def begin_drag(self, event):
        snippet_id = self.GetItemData(event.GetIndex())
        wx.CallAfter(self._start_drag, snippet_id)

    def _start_drag(self, snippet_id):
        data = wx.TextDataObject("snippet:{}".format(snippet_id))
        source = wx.DropSource(self)
        source.SetData(data)
        source.DoDragDrop(wx.Drag_AllowMove)

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
                style=wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
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
        if snippet.id is not None and self.FindItem(-1, snippet.id) != wx.NOT_FOUND:
            self.focus_id(snippet.id)
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
            self.add_snippet_in_list(snippet)
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
