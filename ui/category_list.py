import pymitter
import wx

import datamodel
from ui import utils
from ui.transfer import TransferBuffer


class _CategoryDropTarget(wx.TextDropTarget):
    def __init__(self, tree):
        super().__init__()
        self._tree = tree

    def OnDropText(self, x, y, data):
        item, _flags = self._tree.HitTest((x, y))
        if not item.IsOk():
            return False
        category_id = self._tree.GetItemData(item)
        try:
            kind, value = data.split(":", 1)
            entity_id = int(value)
        except (ValueError, TypeError):
            return False
        return self._tree.transfer_to(kind, entity_id, category_id, copy=False)


class CategoryList(wx.TreeCtrl):
    """Accessible category tree.

    Ctrl+C/Ctrl+X copy or cut the selected category. Ctrl+V pastes the
    application-local item (category or snippet) below the selected category.
    """

    def __init__(
        self,
        parent,
        ee: pymitter.EventEmitter,
        model: datamodel.DataModel,
        transfer_buffer: TransferBuffer,
    ):
        super().__init__(
            parent,
            style=wx.TR_HAS_BUTTONS
            | wx.TR_LINES_AT_ROOT
            | wx.TR_SINGLE
            | wx.TR_HIDE_ROOT,
        )
        self._ee = ee
        self._model = model
        self._transfer_buffer = transfer_buffer
        self._items = {}
        self._empty_item = None
        self._images = wx.ImageList(16, 16)
        self._images.Add(
            wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (16, 16))
        )
        self.AssignImageList(self._images)
        self._root = self.AddRoot("Categories")
        self.SetDropTarget(_CategoryDropTarget(self))
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.selection_changed)
        self.Bind(wx.EVT_TREE_BEGIN_DRAG, self.begin_drag)
        self.Bind(wx.EVT_CONTEXT_MENU, self.context_menu)
        self.Bind(wx.EVT_CHAR_HOOK, self.key_handler)
        for event_name in (
            "category.added",
            "category.edited",
            "category.deleted",
            "snippet.added",
            "snippet.edited",
            "snippet.deleted",
        ):
            ee.on(event_name, self._on_model_changed)
        self.update()

    def _label(self, category: datamodel.Category) -> str:
        return "{} ({})".format(category.name, category.number_of_snippets)

    def update(self, *args):
        selected_id = self.get_selected_id()
        expanded_ids = {
            category_id
            for category_id, item in self._items.items()
            if self.IsExpanded(item)
        }
        self.Freeze()
        self.DeleteChildren(self._root)
        self._items.clear()
        self._empty_item = None
        self._append_children(self._root, None)
        if not self._items:
            self._empty_item = self.AppendItem(
                self._root,
                "No categories",
            )
            self.SetItemData(self._empty_item, None)
            self.SelectItem(self._empty_item)
        for category_id in expanded_ids:
            item = self._items.get(category_id)
            if item is not None:
                self.Expand(item)
        if selected_id is not None:
            self.focus_id(selected_id)
        self.Thaw()

    def _append_children(self, parent_item, parent_id):
        for category in self._model.get_category_children(parent_id):
            item = self.AppendItem(
                parent_item,
                self._label(category),
                image=0,
            )
            self.SetItemData(item, category.id)
            self._items[category.id] = item
            self._append_children(item, category.id)

    def get_selected_id(self):
        item = self.GetSelection()
        if not item.IsOk() or item == self._root:
            return None
        return self.GetItemData(item)

    def focus_id(self, category_id: int, select: bool = True):
        item = self._items.get(category_id)
        if item is None:
            return False
        parent = self.GetItemParent(item)
        while parent.IsOk() and parent != self._root:
            self.Expand(parent)
            parent = self.GetItemParent(parent)
        if select:
            self.SelectItem(item)
        self.EnsureVisible(item)
        return True

    def selection_changed(self, event):
        self._ee.emit("category_list.changed", self.get_selected_id())
        event.Skip()

    def context_menu(self, event):
        menu = wx.Menu()
        new_root = menu.Append(
            wx.ID_ANY,
            "New top-level category\tCtrl+N",
        )
        menu.Bind(wx.EVT_MENU, lambda evt: self.add_category(None), new_root)
        paste_root = menu.Append(
            wx.ID_ANY,
            "Paste as top-level\tCtrl+Shift+V",
        )
        paste_root.Enable(self._transfer_buffer.value is not None)
        menu.Bind(wx.EVT_MENU, lambda evt: self.paste(evt, None), paste_root)
        category_id = self.get_selected_id()
        if category_id is not None:
            new_child = menu.Append(
                wx.ID_ANY,
                "New subcategory\tCtrl+Shift+N",
            )
            menu.Bind(
                wx.EVT_MENU,
                lambda evt: self.add_category(category_id),
                new_child,
            )
            menu.AppendSeparator()
            copy_item = menu.Append(wx.ID_COPY, "Copy\tCtrl+C")
            cut_item = menu.Append(wx.ID_CUT, "Cut\tCtrl+X")
            paste_item = menu.Append(wx.ID_PASTE, "Paste into\tCtrl+V")
            paste_item.Enable(self._transfer_buffer.value is not None)
            menu.Bind(wx.EVT_MENU, lambda evt: self.copy_or_cut(True), copy_item)
            menu.Bind(wx.EVT_MENU, lambda evt: self.copy_or_cut(False), cut_item)
            menu.Bind(
                wx.EVT_MENU,
                lambda evt: self.paste(evt, category_id),
                paste_item,
            )
            menu.AppendSeparator()
            edit_item = menu.Append(wx.ID_ANY, "Rename\tF2")
            delete_item = menu.Append(wx.ID_DELETE, "Delete\tDelete")
            menu.Bind(wx.EVT_MENU, self.edit_category, edit_item)
            menu.Bind(wx.EVT_MENU, self.delete_category, delete_item)
        self.PopupMenu(menu)
        menu.Destroy()

    def key_handler(self, event):
        key = event.GetKeyCode()
        if event.ControlDown() and key in (ord("C"), 3, ord("X"), 24):
            self.copy_or_cut(key in (ord("C"), 3))
        elif event.ControlDown() and key in (ord("V"), 22):
            destination_id = None if event.ShiftDown() else self.get_selected_id()
            self.paste(event, destination_id)
        elif event.ControlDown() and key in (ord("N"), 14):
            parent_id = self.get_selected_id() if event.ShiftDown() else None
            self.add_category(parent_id)
        elif key == wx.WXK_F2:
            self.edit_category(event)
        elif key == wx.WXK_DELETE:
            self.delete_category(event)
        else:
            event.Skip()

    def add_category(self, parent_id):
        with utils.managed_dialog(
            wx.TextEntryDialog(
                self,
                "Enter the name of the new category",
                "Add category",
            )
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            name = dialog.GetValue()
        try:
            category = self._model.add_category(
                datamodel.Category(name=name, parent_id=parent_id)
            )
            self.update()
            self.focus_id(category.id)
        except datamodel.DataModelError as error:
            self._show_error(error)

    def edit_category(self, event):
        category_id = self.get_selected_id()
        if category_id is None:
            return
        try:
            category = self._model.get_category(category_id)
        except datamodel.DataModelError as error:
            self._show_error(error)
            self.update()
            return
        with utils.managed_dialog(
            wx.TextEntryDialog(
                self,
                "Enter the new name of the category",
                "Rename category",
                value=category.name,
            )
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            category.name = dialog.GetValue()
        try:
            self._model.edit_category(category)
        except datamodel.DataModelError as error:
            self._show_error(error)

    def delete_category(self, event):
        category_id = self.get_selected_id()
        if category_id is None:
            return
        focus_target_id = self._get_focus_target_after_delete(category_id)
        try:
            category = self._model.get_category(category_id)
            descendants, snippets = self._model.get_category_subtree_stats(
                category_id
            )
        except datamodel.DataModelError as error:
            self._show_error(error)
            self.update()
            return
        message = (
            "Delete category '{}', {} subcategories and {} snippets?"
        ).format(category.name, descendants, snippets)
        with utils.managed_dialog(
            wx.MessageDialog(
                self,
                message,
                "Delete category",
                style=wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            )
        ) as dialog:
            if dialog.ShowModal() != wx.ID_YES:
                return
        try:
            self._model.delete_category(category_id)
        except datamodel.DataModelError as error:
            self._show_error(error)
            return
        wx.CallAfter(self._focus_after_delete, focus_target_id)

    def _get_focus_target_after_delete(self, category_id):
        item = self._items.get(category_id)
        if item is None:
            return None
        for candidate in (
            self.GetNextSibling(item),
            self.GetPrevSibling(item),
            self.GetItemParent(item),
        ):
            if candidate.IsOk() and candidate != self._root:
                return self.GetItemData(candidate)
        return None

    def _focus_after_delete(self, preferred_category_id):
        if (
            preferred_category_id is not None
            and self.focus_id(preferred_category_id)
        ):
            self.SetFocus()
            return
        root_categories = list(self._model.get_category_children(None))
        if root_categories:
            self.focus_id(root_categories[0].id)
        elif self._empty_item is not None and self._empty_item.IsOk():
            self.SelectItem(self._empty_item)
            self.EnsureVisible(self._empty_item)
        self.SetFocus()

    def copy_or_cut(self, copy):
        category_id = self.get_selected_id()
        if category_id is None:
            return
        self._transfer_buffer.set("category", category_id, copy)
        action = "Copied" if copy else "Cut"
        self._ee.emit(
            "status.changed",
            "{} category. Select a destination and press Ctrl+V.".format(action),
        )

    def paste(self, event, destination_id):
        transfer = self._transfer_buffer.value
        if transfer is None:
            wx.Bell()
            return
        if destination_id is None and transfer.kind == "snippet":
            wx.MessageBox(
                "A snippet must be pasted into a category.",
                "Paste snippet",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        if self.transfer_to(
            transfer.kind,
            transfer.entity_id,
            destination_id,
            transfer.copy,
        ) and not transfer.copy:
            self._transfer_buffer.clear()

    def transfer_to(self, kind, entity_id, destination_id, copy):
        try:
            if kind == "category":
                if copy:
                    result = self._model.copy_category(
                        entity_id,
                        destination_id,
                    )
                else:
                    result = self._model.move_category(
                        entity_id,
                        destination_id,
                    )
                self.update()
                self.focus_id(result.id)
            elif kind == "snippet":
                if copy:
                    self._model.copy_snippet(entity_id, destination_id)
                else:
                    self._model.move_snippet(entity_id, destination_id)
                self.focus_id(destination_id)
            else:
                return False
        except datamodel.DataModelError as error:
            self._show_error(error)
            return False
        self._ee.emit("status.changed", "Transfer completed.")
        return True

    def begin_drag(self, event):
        category_id = self.GetItemData(event.GetItem())
        event.Veto()
        wx.CallAfter(self._start_drag, category_id)

    def _start_drag(self, category_id):
        data = wx.TextDataObject("category:{}".format(category_id))
        source = wx.DropSource(self)
        source.SetData(data)
        source.DoDragDrop(wx.Drag_AllowMove)

    def _on_model_changed(self, value):
        self.update()

    def _show_error(self, error):
        wx.MessageBox(
            str(error),
            "Category error",
            wx.OK | wx.ICON_ERROR,
            self,
        )
