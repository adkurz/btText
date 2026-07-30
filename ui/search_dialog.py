"""Debounced full-text snippet search dialog."""

import wx

from core import datamodel
from core.error_messages import format_user_error
from i18n import _
from ui import utils


SEARCH_DELAY_MS = 300
CONTENT_PREVIEW_LENGTH = 60


class SearchDialog(wx.Dialog):
    """Search snippets without querying SQLite on every keystroke."""
    def __init__(self, parent, model: datamodel.DataModel):
        """Build the search controls and delayed-query timer."""
        super().__init__(
            parent,
            # Translators: Window title for finding snippets.
            title=_("Search snippets"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._model = model
        self._selected_snippet_id = None
        self._search_timer = wx.Timer(self)

        pane = wx.Panel(self)
        # Translators: Label for the text field used to search snippets.
        # "&" marks the keyboard mnemonic for the adjacent field.
        search_label = wx.StaticText(pane, label=_("&Search"))
        self.search_input = wx.TextCtrl(pane)
        # Translators: Label for the list of snippets matching the search.
        # "&" marks the keyboard mnemonic for the adjacent result list.
        result_label = wx.StaticText(pane, label=_("Search &results"))
        self.result_list = wx.ListView(
            pane,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL,
        )
        # Translators: Search-results column containing each snippet's name.
        self.result_list.AppendColumn(_("Name"), width=self.FromDIP(210))
        # Translators: Search-results column containing the snippet's category.
        self.result_list.AppendColumn(_("Category"), width=self.FromDIP(180))
        # Translators: Search-results column containing the snippet's search rank.
        self.result_list.AppendColumn(_("Weight"), width=self.FromDIP(90))
        self.result_list.AppendColumn(
            # Translators: Search-results column showing the beginning of the
            # snippet text.
            _("Content preview"),
            width=self.FromDIP(330),
        )

        # Translators: Search-dialog button that selects the highlighted result
        # in the main window and closes the dialog. "&" marks the mnemonic.
        self.open_button = wx.Button(pane, wx.ID_OK, _("&Show snippet"))
        self.open_button.Enable(False)
        # Translators: Search-dialog button that closes the dialog without
        # selecting a result. "&" marks the keyboard mnemonic.
        cancel_button = wx.Button(pane, wx.ID_CANCEL, _("&Cancel"))

        button_sizer = wx.StdDialogButtonSizer()
        button_sizer.AddButton(self.open_button)
        button_sizer.AddButton(cancel_button)
        button_sizer.Realize()
        self.SetAffirmativeId(wx.ID_OK)
        self.open_button.SetDefault()

        pane_sizer = wx.BoxSizer(wx.VERTICAL)
        pane_sizer.Add(search_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        pane_sizer.Add(
            self.search_input,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            10,
        )
        pane_sizer.Add(
            result_label,
            0,
            wx.LEFT | wx.RIGHT,
            10,
        )
        pane_sizer.Add(
            self.result_list,
            1,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            10,
        )
        pane_sizer.Add(
            button_sizer,
            0,
            wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            10,
        )
        pane.SetSizer(pane_sizer)

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(pane, 1, wx.EXPAND)
        self.SetSizer(dialog_sizer)
        self.SetMinSize(self.FromDIP((700, 440)))
        self.SetSize(self.FromDIP((900, 580)))
        self.CentreOnParent()

        self.Bind(wx.EVT_TIMER, self._on_search_timer, self._search_timer)
        self.search_input.Bind(wx.EVT_TEXT, self._on_search_text_changed)
        self.result_list.Bind(
            wx.EVT_LIST_ITEM_FOCUSED,
            self._on_result_focused,
        )
        self.result_list.Bind(
            wx.EVT_LIST_ITEM_SELECTED,
            self._on_result_focused,
        )
        self.result_list.Bind(
            wx.EVT_LIST_ITEM_ACTIVATED,
            self._on_result_activated,
        )
        self.open_button.Bind(wx.EVT_BUTTON, self._on_open)

        self.search_input.SetFocus()

    def _on_search_text_changed(self, event: wx.CommandEvent):
        """Restart the debounce interval after the query changes."""
        # Restarting the one-shot timer coalesces rapid typing into one query.
        self._search_timer.Stop()
        self._selected_snippet_id = None
        self.open_button.Enable(False)
        if not self.search_input.GetValue():
            self.result_list.DeleteAllItems()
            return
        self._search_timer.StartOnce(SEARCH_DELAY_MS)

    def _on_search_timer(self, event: wx.TimerEvent):
        """Run the pending query after the debounce timer expires."""
        self._run_search()

    def _run_search(self):
        """Populate the result list from the current literal search term."""
        term = self.search_input.GetValue()
        self.result_list.Freeze()
        try:
            self.result_list.DeleteAllItems()
            self._selected_snippet_id = None
            self.open_button.Enable(False)
            if not term:
                return

            category_names = {}
            for snippet in self._model.search_snippets(term):
                if snippet.category_id not in category_names:
                    category_names[snippet.category_id] = (
                        self._model.get_category_path(snippet.category_id)
                    )
                index = self.result_list.Append(
                    (
                        snippet.name,
                        category_names[snippet.category_id],
                        utils.get_weight_string(snippet.weight),
                        utils.reduce_string(
                            snippet.content,
                            CONTENT_PREVIEW_LENGTH,
                        ),
                    )
                )
                self.result_list.SetItemData(index, snippet.id or 0)
        except datamodel.DataModelError as error:
            wx.MessageBox(
                format_user_error(error),
                # Translators: Title of an error while searching snippets.
                _("Search error"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
        finally:
            self.result_list.Thaw()

    def _on_result_focused(self, event: wx.ListEvent):
        """Remember the model ID associated with the focused result."""
        self._selected_snippet_id = self.result_list.GetItemData(
            event.GetIndex()
        )
        self.open_button.Enable(True)

    def _on_result_activated(self, event: wx.ListEvent):
        """Accept a result activated by keyboard or mouse."""
        self._on_result_focused(event)
        self._accept_selection()

    def _on_open(self, event: wx.CommandEvent):
        """Accept the currently selected search result."""
        self._accept_selection()

    def _accept_selection(self):
        """Close successfully when a valid result is selected."""
        if self._selected_snippet_id is not None:
            self.EndModal(wx.ID_OK)

    def get_selected_snippet(self) -> datamodel.Snippet | None:
        """Return the accepted snippet, or ``None`` if none was selected."""
        if self._selected_snippet_id is None:
            return None
        return self._model.get_snippet(self._selected_snippet_id)

    def Destroy(self):
        """Stop the owned timer before destroying the native dialog."""
        self._search_timer.Stop()
        return super().Destroy()
