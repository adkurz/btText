"""List view and editing commands for snippets in the selected category."""

from collections.abc import Callable

import wx

from platform_support import clipboard, clipboard_paste
from core import datamodel
from core.error_messages import format_user_error
from core.events import EventEmitter
from core.variables import RenderedSnippet
from i18n import _, ngettext
from ui import utils
from ui.snippet_editor import SnippetEditor
from ui.transfer import TransferBuffer
from ui.variable_dialog import VariableSuggestion

CONTENT_PREVIEW_LENGTH = 40


class SnippetList(wx.ListView):
    """Present snippets and synchronize rows with model events."""

    def __init__(
        self,
        parent,
        ee: EventEmitter,
        model: datamodel.DataModel,
        transfer_buffer: TransferBuffer,
        include_copied_text_in_clipboard_history: Callable[[], bool],
        allow_copied_text_cloud_upload: Callable[[], bool],
        render_snippet: Callable[[str], RenderedSnippet],
        validate_snippet: Callable[[str], None],
        variable_suggestions: tuple[VariableSuggestion, ...],
    ):
        """Build columns, commands, and model-event subscriptions."""
        super().__init__(
            parent,
            style=wx.LC_REPORT | wx.LC_SORT_ASCENDING,
        )
        self._ee = ee
        self._model = model
        self._transfer_buffer = transfer_buffer
        self._include_copied_text_in_clipboard_history = (
            include_copied_text_in_clipboard_history
        )
        self._allow_copied_text_cloud_upload = allow_copied_text_cloud_upload
        self._render_snippet = render_snippet
        self._validate_snippet = validate_snippet
        self._variable_suggestions = variable_suggestions
        self.selected_category_id = None
        header_font = wx.Font(self.GetFont())
        header_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self._header_attributes = wx.ItemAttr(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNTEXT),
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE),
            header_font,
        )
        self.SetHeaderAttr(self._header_attributes)
        # Translators: Snippet-list column containing each snippet's name.
        self.AppendColumn(_("Name"), width=self.FromDIP(220))
        # Translators: Snippet-list column containing the localized search rank.
        self.AppendColumn(_("Weight"), width=self.FromDIP(100))
        # Translators: Accessible name for a hidden numeric sort column that
        # corresponds to the visible snippet weight.
        weight_number = self.AppendColumn(_("Weight number"))
        # Sort by the hidden numeric value, not the localized weight label.
        self.SetColumnWidth(weight_number, 0)
        # Translators: Snippet-list column showing the beginning of its content.
        self.AppendColumn(_("Content preview"), width=self.FromDIP(420))
        self.Bind(wx.EVT_CONTEXT_MENU, self.context_menu)
        self.Bind(wx.EVT_CHAR, self.key_handler)
        self.Bind(wx.EVT_LIST_BEGIN_DRAG, self.begin_drag)
        ee.on("category_tree.changed", self.update)
        ee.on("category.deleted", self.category_deleted)
        ee.on("snippet.added", self.add_snippet_in_list)
        ee.on("snippet.edited", self.edit_snippet_in_list)
        ee.on("snippet.deleted", self.delete_snippet_from_list)

    def get_selected_id(self):
        """Return the model ID of the first selected row, if any."""
        index = self.GetFirstSelected()
        return self.GetItemData(index) if index != wx.NOT_FOUND else None

    def get_selected_ids(self):
        """Return model IDs for all selected rows in display order."""
        ids = []
        index = self.GetFirstSelected()
        while index != wx.NOT_FOUND:
            ids.append(self.GetItemData(index))
            index = self.GetNextSelected(index)
        return ids

    def focus_id(self, snippet_id: int, select: bool = True):
        """Focus and optionally select a snippet row by model ID."""
        index = self.FindItem(-1, snippet_id)
        if index == wx.NOT_FOUND:
            return False
        self.Focus(index)
        if select:
            self.Select(index)
        return True

    def sort(self):
        """Sort rows by weight and name."""
        self.SortItems(self._sort_compare)

    def category_deleted(self, category_id: int):
        """Clear rows when their selected category was deleted."""
        if category_id == self.selected_category_id:
            self.update(None, force=True)

    def update(self, category_id: int | None, force: bool = False):
        """Reload rows when the selected category changes."""
        if category_id == self.selected_category_id and not force:
            return
        self.selected_category_id = category_id
        with utils.frozen(self):
            self.DeleteAllItems()
            if category_id is None:
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
            if self.GetItemCount():
                self.Focus(0)

    def context_menu(self, event: wx.ContextMenuEvent):
        """Show commands valid for the current row and transfer state."""
        menu = wx.Menu()
        # Translators: Snippet-list menu command that opens the editor to create
        # a snippet in the selected category. Keep Ctrl+N after "\t".
        new_snippet = menu.Append(wx.ID_ANY, _("New snippet\tCtrl+N"))
        menu.Bind(wx.EVT_MENU, self.add_snippet, new_snippet)
        if self.selected_category_id is not None:
            paste_item = menu.Append(
                wx.ID_PASTE,
                # Translators: Snippet-list menu command that pastes a copied or
                # cut category into the current category. Keep Ctrl+V after "\t".
                _("Paste into category\tCtrl+V"),
            )
            paste_item.Enable(self._transfer_buffer.value is not None)
            menu.Bind(wx.EVT_MENU, self.paste, paste_item)
        selected_ids = self.get_selected_ids()
        if selected_ids:
            if len(selected_ids) == 1:
                insert_snippet = menu.Append(
                    wx.ID_ANY,
                    # Translators: Snippet-list menu command that inserts the
                    # selected snippet into the previously active application.
                    # Keep Enter after "\t".
                    _("Insert snippet\tEnter"),
                )
                menu.Bind(wx.EVT_MENU, self.insert_snippet, insert_snippet)
                copy_text = menu.Append(
                    wx.ID_ANY,
                    # Translators: Snippet-list menu command that copies the
                    # selected snippet's text to the Windows clipboard. Keep
                    # Ctrl+Shift+C after "\t".
                    _("Copy text to clipboard\tCtrl+Shift+C"),
                )
                menu.Bind(wx.EVT_MENU, self.copy_text_to_clipboard, copy_text)
                edit_snippet = menu.Append(
                    wx.ID_ANY,
                    # Translators: Snippet-list menu command that opens the
                    # selected snippet in the editor. Keep F2 after "\t".
                    _("Edit snippet\tF2"),
                )
                menu.Bind(wx.EVT_MENU, self.edit_snippet, edit_snippet)
            menu.AppendSeparator()
            selected_count = len(selected_ids)
            copy_snippet = menu.Append(
                wx.ID_COPY,
                # Translators: Snippet-list menu command that copies the selected
                # snippet or snippets. Keep Ctrl+C after "\t".
                ngettext(
                    "Copy snippet\tCtrl+C",
                    "Copy snippets\tCtrl+C",
                    selected_count,
                ),
            )
            cut_snippet = menu.Append(
                wx.ID_CUT,
                # Translators: Snippet-list menu command that cuts the selected
                # snippet or snippets. Keep Ctrl+X after "\t".
                ngettext(
                    "Cut snippet\tCtrl+X",
                    "Cut snippets\tCtrl+X",
                    selected_count,
                ),
            )
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
            delete_snippets = menu.Append(
                wx.ID_DELETE,
                # Translators: Snippet-list menu command that deletes the selected
                # snippet or snippets. The final "Delete" is the keyboard key.
                ngettext(
                    "Delete snippet\tDelete",
                    "Delete snippets\tDelete",
                    selected_count,
                ),
            )
            menu.Bind(wx.EVT_MENU, self.delete_snippet, delete_snippets)
        utils.popup_menu(self, menu)

    def key_handler(self, event: wx.KeyEvent):
        """Map keyboard shortcuts to snippet operations."""
        key = event.GetKeyCode()
        if event.ControlDown() and event.ShiftDown() and key in (ord("C"), 3):
            self.copy_text_to_clipboard(event)
        elif event.ControlDown() and key in (ord("C"), 3, ord("X"), 24):
            self.copy_or_cut(key in (ord("C"), 3))
        elif event.ControlDown() and key in (ord("A"), 1):
            for index in range(self.GetItemCount()):
                self.Select(index)
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

    def copy_text_to_clipboard(
        self,
        event: wx.CommandEvent | wx.KeyEvent,
    ):
        """Copy the single selected snippet's content to the Windows clipboard."""
        snippet_ids = self.get_selected_ids()
        if len(snippet_ids) != 1:
            wx.Bell()
            return
        try:
            snippet = self._model.get_snippet(snippet_ids[0])
            clipboard.copy_text(
                snippet.content,
                include_in_history=(self._include_copied_text_in_clipboard_history()),
                allow_cloud_upload=self._allow_copied_text_cloud_upload(),
            )
        except (datamodel.DataModelError, clipboard.ClipboardError) as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Title of an error copying snippet text to the
                # Windows clipboard.
                _("Clipboard error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        # Translators: Status after a snippet's text was copied to the Windows
        # clipboard.
        self._ee.emit("status.changed", _("Text copied to clipboard."))

    def copy_or_cut(self, copy: bool):
        """Place all selected snippets in the local transfer buffer."""
        snippet_ids = self.get_selected_ids()
        if not snippet_ids:
            return
        self._transfer_buffer.set("snippet", snippet_ids, copy)
        snippet_count = len(snippet_ids)
        if copy:
            # Translators: Status after copying snippets; they are not pasted
            # yet. Copies omit globally unique hotstrings. {count} is the
            # number copied, and Ctrl+V is the paste shortcut.
            message = ngettext(
                "Copied {count} snippet. Its hotstring will not be included "
                "when pasted. Select a category and press Ctrl+V.",
                "Copied {count} snippets. Their hotstrings will not be included "
                "when pasted. Select a category and press Ctrl+V.",
                snippet_count,
            )
        else:
            # Translators: Status after cutting snippets; they are not moved yet.
            # {count} is the number cut, and Ctrl+V is the paste shortcut.
            message = ngettext(
                "Cut {count} snippet. Select a category and press Ctrl+V.",
                "Cut {count} snippets. Select a category and press Ctrl+V.",
                snippet_count,
            )
        self._ee.emit(
            "status.changed",
            message.format(count=snippet_count),
        )

    def paste(self, event, as_top_level: bool = False):
        """Apply the pending entity transfer at the selected destination."""
        transfer = self._transfer_buffer.value
        category_id = self.selected_category_id
        if transfer is None:
            wx.Bell()
            return
        if as_top_level:
            if transfer.kind != "category":
                wx.MessageBox(
                    # Translators: Explains that the top-level paste command only
                    # accepts a copied or cut category, not snippets.
                    _("Only a category can be pasted as a top-level category."),
                    # Translators: Title of information about pasting a category
                    # at the category-tree root.
                    _("Paste as top-level"),
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
                    snippets = self._model.copy_snippets(
                        transfer.entity_ids,
                        category_id,
                    )
                else:
                    snippets = self._model.move_snippets(
                        transfer.entity_ids,
                        category_id,
                    )
                for snippet in snippets:
                    if snippet.id is not None:
                        self.focus_id(snippet.id)
            else:
                return
        except datamodel.DataModelError as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Title of an error while pasting copied or cut items.
                _("Paste error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        if not transfer.copy:
            self._transfer_buffer.clear()
        item_count = len(transfer.entity_ids)
        # Translators: Status after a pending copy or cut operation is pasted.
        # {count} includes all transferred categories and snippets.
        message = ngettext(
            "Transferred {count} item.",
            "Transferred {count} items.",
            item_count,
        ).format(count=item_count)
        self._ee.emit(
            "status.changed",
            message,
        )

    def begin_drag(self, event):
        """Capture the dragged snippet and defer native drag startup."""
        snippet_id = self.GetItemData(event.GetIndex())
        wx.CallAfter(self._start_drag, snippet_id)

    def _start_drag(self, snippet_id):
        """Start an internal move drag for a snippet."""
        data = wx.TextDataObject("snippet:{}".format(snippet_id))
        source = wx.DropSource(self)
        source.SetData(data)
        source.DoDragDrop(wx.Drag_AllowMove)

    def insert_snippet(self, event: wx.CommandEvent | wx.KeyEvent):
        """Request insertion of the selected snippet into another window."""
        snippet_id = self.get_selected_id()
        if snippet_id is not None:
            self._ee.emit("snippet.insert_requested", snippet_id)

    def add_snippet(self, event: wx.CommandEvent | wx.KeyEvent):
        """Open an editor for a new snippet in the selected category."""
        if self.selected_category_id is None:
            return
        with utils.managed_dialog(
            SnippetEditor(
                self.GetGrandParent(),
                self._ee,
                self._model,
                self.selected_category_id,
                self._render_snippet,
                self._validate_snippet,
                self._variable_suggestions,
            )
        ) as editor:
            editor.ShowModal()

    def edit_snippet(self, event: wx.CommandEvent | wx.KeyEvent):
        """Open an editor for the selected snippet."""
        snippet_id = self.get_selected_id()
        if snippet_id is None or self.selected_category_id is None:
            return
        try:
            snippet = self._model.get_snippet(snippet_id)
        except datamodel.EntityNotFoundError as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Generic title for a failed snippet-list operation.
                _("Error"),
                style=wx.OK | wx.ICON_ERROR,
            )
            self.update(self.selected_category_id, force=True)
            return
        with utils.managed_dialog(
            SnippetEditor(
                self.GetGrandParent(),
                self._ee,
                self._model,
                self.selected_category_id,
                self._render_snippet,
                self._validate_snippet,
                self._variable_suggestions,
                snippet,
            )
        ) as editor:
            editor.ShowModal()

    def delete_snippet(self, event: wx.CommandEvent | wx.KeyEvent):
        """Confirm and delete all selected snippets."""
        snippet_ids = self.get_selected_ids()
        if not snippet_ids:
            return
        try:
            snippets = [
                self._model.get_snippet(snippet_id) for snippet_id in snippet_ids
            ]
        except datamodel.EntityNotFoundError as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Generic title for a failed snippet-list operation.
                _("Error"),
                style=wx.OK | wx.ICON_ERROR,
            )
            self.update(self.selected_category_id, force=True)
            return
        if len(snippets) == 1:
            # Translators: Confirmation before permanently deleting one snippet.
            # {name} is the snippet's name.
            message = _("Do you want to delete the snippet '{name}'?").format(
                name=snippets[0].name
            )
            # Translators: Title of the confirmation for deleting one snippet.
            title = _("Delete snippet?")
        else:
            # Translators: Confirmation before permanently deleting several
            # selected snippets. {count} is the number selected.
            message = ngettext(
                "Do you want to delete {count} selected snippet?",
                "Do you want to delete {count} selected snippets?",
                len(snippets),
            ).format(count=len(snippets))
            # Translators: Title of the confirmation for deleting multiple snippets.
            title = _("Delete snippets?")
        if not utils.confirm_yes_no(self, message, title):
            return
        focus_id = self._get_focus_target_after_delete(set(snippet_ids))
        try:
            self._model.delete_snippets(snippet_ids)
        except datamodel.DataModelError as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Generic title for a failed snippet deletion.
                _("Error"),
                style=wx.OK | wx.ICON_ERROR,
            )
            self.update(self.selected_category_id, force=True)
            return
        transfer = self._transfer_buffer.value
        if (
            transfer is not None
            and transfer.kind == "snippet"
            and set(transfer.entity_ids).intersection(snippet_ids)
        ):
            self._transfer_buffer.clear()
        if focus_id is not None:
            self.focus_id(focus_id)
        self.SetFocus()
        # Translators: Status after selected snippets were permanently deleted.
        # {count} is the number deleted.
        message = ngettext(
            "Deleted {count} snippet.",
            "Deleted {count} snippets.",
            len(snippet_ids),
        ).format(count=len(snippet_ids))
        self._ee.emit(
            "status.changed",
            message,
        )

    def _get_focus_target_after_delete(self, deleted_ids: set[int]):
        """Choose the closest surviving row for keyboard focus."""
        selected_index = self.GetFirstSelected()
        if selected_index == wx.NOT_FOUND:
            return None
        for index in range(selected_index, self.GetItemCount()):
            candidate_id = self.GetItemData(index)
            if candidate_id not in deleted_ids:
                return candidate_id
        for index in range(selected_index - 1, -1, -1):
            candidate_id = self.GetItemData(index)
            if candidate_id not in deleted_ids:
                return candidate_id
        return None

    def delete_snippet_from_list(self, snippet: datamodel.Snippet):
        """Remove a deleted or moved snippet row by model ID."""
        index = self.FindItem(-1, snippet.id)
        if index == wx.NOT_FOUND:
            return
        self.DeleteItem(index)

    def add_snippet_in_list(self, snippet: datamodel.Snippet):
        """Insert and focus a model-created snippet in the active list."""
        if snippet.category_id != self.selected_category_id:
            return
        if snippet.id is not None and self.FindItem(-1, snippet.id) != wx.NOT_FOUND:
            self.focus_id(snippet.id)
            return
        with utils.frozen(self):
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

    def edit_snippet_in_list(self, snippet: datamodel.Snippet):
        """Update, add, or remove a row after a snippet edit."""
        if snippet.category_id != self.selected_category_id:
            self.delete_snippet_from_list(snippet)
            return
        if snippet.id is None:
            return
        index = self.FindItem(-1, snippet.id)
        if index == wx.NOT_FOUND:
            self.add_snippet_in_list(snippet)
            return
        with utils.frozen(self):
            self.SetItem(index, 0, snippet.name)
            self.SetItem(index, 1, utils.get_weight_string(snippet.weight))
            self.SetItem(index, 2, str(snippet.weight))
            self.SetItem(
                index,
                3,
                utils.reduce_string(snippet.content, CONTENT_PREVIEW_LENGTH),
            )
            self.sort()
            self.focus_id(snippet.id)

    def _sort_compare(self, item1, item2):
        """Sort by descending weight and then by name."""
        weight1 = int(self.GetItemText(self.FindItem(-1, item1), 2))
        weight2 = int(self.GetItemText(self.FindItem(-1, item2), 2))
        weight_result = (weight1 < weight2) - (weight1 > weight2)
        if weight_result != 0:
            return weight_result
        name1 = self.GetItemText(self.FindItem(-1, item1)).casefold()
        name2 = self.GetItemText(self.FindItem(-1, item2)).casefold()
        return (name1 > name2) - (name1 < name2)
