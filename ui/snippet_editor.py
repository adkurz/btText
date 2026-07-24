"""Modal editor for creating and updating snippets."""

import wx
import pymitter

import datamodel
import ui.validators as validators
from ui import utils


class SnippetEditor(wx.Dialog):
    """Edit one snippet and delegate validation to the data model."""
    def __init__(self, parent, ee: pymitter.EventEmitter, model: datamodel.DataModel, category_id: int, snippet: datamodel.Snippet|None = None):
        """Build an editor for a new snippet or an existing snippet."""
        super().__init__(
            parent,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        # Set title:
        if snippet is None:  # Add new snippet
            self.SetTitle("Add snippet")
        else:
            self.SetTitle("Edit snippet")
        self.ee = ee
        self._model = model
        self._snippet = snippet
        self.pane = wx.Panel(self)
        form_sizer = wx.FlexGridSizer(cols=2, vgap=self.FromDIP(10), hgap=self.FromDIP(12))
        form_sizer.AddGrowableCol(1, 1)
        form_sizer.AddGrowableRow(3, 1)

        # Create fields.
        self.name_label = wx.StaticText(self.pane, label="&Name")
        self.name_input = wx.TextCtrl(self.pane, validator=validators.NonEmptyValidator())
        self.category_label = wx.StaticText(self.pane, label="&Category")
        categories_with_paths = [
            (self._model.get_category_path(category.id), category)
            for category in self._model.get_categories()
            if category.id is not None
        ]
        categories_with_paths.sort(key=lambda item: item[0].casefold())
        self._categories = [
            category for _path, category in categories_with_paths
        ]
        self.category_input = wx.Choice(
            self.pane,
            choices=[path for path, _category in categories_with_paths],
        )
        # Preselect current category:
        if category_id is not None:
            for index, category in enumerate(self._categories):
                if category.id == category_id:
                    self.category_input.SetSelection(index)
                    break
        else:
            self.category_input.SetSelection(0)
        self.weight_input = wx.RadioBox(
            self.pane,
            label="&Weight",
            choices=[
                utils.get_weight_string(weight)
                for weight in self._model.WEIGHTS
            ],
        )
        self.content_label = wx.StaticText(self.pane, label="C&ontent")
        self.content_input = wx.TextCtrl(self.pane, style=wx.TE_MULTILINE | wx.TE_RICH2, validator=validators.NonEmptyValidator())
        form_sizer.Add(self.name_label, 0, wx.ALIGN_CENTER_VERTICAL)
        form_sizer.Add(self.name_input, 0, wx.EXPAND)
        form_sizer.Add(self.category_label, 0, wx.ALIGN_CENTER_VERTICAL)
        form_sizer.Add(self.category_input, 0, wx.EXPAND)
        form_sizer.AddSpacer(0)
        form_sizer.Add(self.weight_input, 0, wx.EXPAND)
        form_sizer.Add(self.content_label, 0, wx.ALIGN_TOP)
        form_sizer.Add(self.content_input, 0, wx.EXPAND)
        pane_sizer = wx.BoxSizer(wx.VERTICAL)
        pane_sizer.Add(form_sizer, 1, wx.EXPAND | wx.ALL, self.FromDIP(12))
        self.pane.SetSizer(pane_sizer)

        # Button-Sizer
        btn_sizer = wx.StdDialogButtonSizer()
        self.save_btn = wx.Button(self, wx.ID_OK, "&Save")
        self.save_btn.Bind(wx.EVT_BUTTON, self.save)
        self.cancel_btn = wx.Button(self, wx.ID_CANCEL, "&Cancel")
        btn_sizer.AddButton(self.save_btn)
        btn_sizer.AddButton(self.cancel_btn)
        btn_sizer.Realize()

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(self.pane, 1, wx.EXPAND)
        dialog_sizer.Add(
            btn_sizer,
            0,
            wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            self.FromDIP(12),
        )
        self.SetSizer(dialog_sizer)
        self.SetMinSize(self.FromDIP((560, 430)))
        self.SetSize(self.FromDIP((720, 560)))
        self.CentreOnParent()
        self.Bind(wx.EVT_SHOW, self._on_show)

        if self._snippet is not None:
            self.load()

    def _on_show(self, event: wx.ShowEvent):
        """Focus the first input after wx has activated the dialog."""
        event.Skip()
        if event.IsShown():
            wx.CallAfter(self.name_input.SetFocus)

    def load(self):
        """Populate controls from the snippet being edited."""
        s = self._snippet
        if s is None:
            return
        self.name_input.SetValue(s.name)
        self.weight_input.SetSelection(s.weight - 1)
        self.content_input.SetValue(s.content)

    def save(self, event):
        """Validate controls and persist the edited snippet."""
        if not self.Validate():
            return
        snippet_name = self.name_input.GetValue()
        category_index = self.category_input.GetSelection()
        if category_index == wx.NOT_FOUND:
            return
        snippet_category_id = self._categories[category_index].id
        if snippet_category_id is None:
            return
        snippet_weight = self.weight_input.GetSelection() + 1
        snippet_content = self.content_input.GetValue()
        snippet = datamodel.Snippet(name=snippet_name, category_id=snippet_category_id, weight=snippet_weight, content=snippet_content)
        try:
            if self._snippet is None: # Add new snippet
                self._model.add_snippet(snippet)
            else: # Edit existing snippet
                snippet.id = self._snippet.id
                self._model.edit_snippet(snippet)
            self.EndModal(wx.OK)
        except datamodel.DataModelError as e:
            wx.MessageBox(str(e), 'Validation error', wx.OK | wx.ICON_ERROR)
