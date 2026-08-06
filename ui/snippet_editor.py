"""Modal editor for creating and updating snippets."""

from collections.abc import Callable

import wx

from core import datamodel
from core.events import EventEmitter
import ui.validators as validators
from core.error_messages import format_user_error
from core.variables import (
    RenderedSnippet,
    VariableError,
    VariableRenderingCancelled,
)
from i18n import _
from ui import utils
from ui.variable_dialog import (
    VariablePickerDialog,
    VariablePreviewDialog,
    VariableSuggestion,
)
from ui.variable_resolver import show_variable_error


class SnippetEditor(wx.Dialog):
    """Edit one snippet and delegate validation to the data model."""

    def __init__(
        self,
        parent,
        ee: EventEmitter,
        model: datamodel.DataModel,
        category_id: int,
        render_snippet: Callable[[str], RenderedSnippet],
        validate_snippet: Callable[[str], None],
        variable_suggestions: tuple[VariableSuggestion, ...],
        snippet: datamodel.Snippet | None = None,
    ):
        """Build an editor for a new snippet or an existing snippet."""
        super().__init__(
            parent,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        # Set title:
        if snippet is None:  # Add new snippet
            # Translators: Window title for creating a snippet.
            self.SetTitle(_("Add snippet"))
        else:
            # Translators: Window title for changing an existing snippet.
            self.SetTitle(_("Edit snippet"))
        self.ee = ee
        self._model = model
        self._snippet = snippet
        self._render_snippet = render_snippet
        self._validate_snippet = validate_snippet
        self._variable_suggestions = variable_suggestions
        self.pane = wx.Panel(self)
        form_sizer = wx.FlexGridSizer(
            cols=2, vgap=self.FromDIP(10), hgap=self.FromDIP(12)
        )
        form_sizer.AddGrowableCol(1, 1)
        form_sizer.AddGrowableRow(4, 1)

        # Create fields.
        # Translators: Label for the editable snippet name. "&" marks the
        # keyboard mnemonic for the adjacent text field.
        self.name_label = wx.StaticText(self.pane, label=_("&Name"))
        self.name_input = wx.TextCtrl(
            self.pane, validator=validators.NonEmptyValidator()
        )
        # Translators: Label for the category in which the snippet is stored.
        # "&" marks the mnemonic for the adjacent category selector.
        self.category_label = wx.StaticText(self.pane, label=_("&Category"))
        categories_with_paths = [
            (self._model.get_category_path(category.id), category)
            for category in self._model.get_categories()
            if category.id is not None
        ]
        categories_with_paths.sort(key=lambda item: item[0].casefold())
        self._categories = [category for _path, category in categories_with_paths]
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
            # Translators: Group label for the snippet's ranking in search
            # results. "&" marks the keyboard mnemonic.
            label=_("&Weight"),
            choices=[utils.get_weight_string(weight) for weight in self._model.WEIGHTS],
        )
        # Translators: Label for the optional abbreviation that expands after
        # the user types a boundary key. "&" marks the keyboard mnemonic.
        self.hotstring_label = wx.StaticText(self.pane, label=_("&Hotstring"))
        self.hotstring_input = wx.TextCtrl(self.pane)
        self.hotstring_input.SetHint(
            # Translators: Hint explaining when an optional hotstring expands.
            _("Optional; expands after Space, Enter, Tab, or punctuation")
        )
        # Translators: Label for the snippet text that will be inserted.
        # "&" marks the mnemonic for the adjacent multiline editor.
        self.content_label = wx.StaticText(self.pane, label=_("C&ontent"))
        self.content_input = wx.TextCtrl(
            self.pane,
            style=wx.TE_MULTILINE | wx.TE_RICH2,
            validator=validators.NonEmptyValidator(),
        )
        self.insert_variable_button = wx.Button(
            self.pane,
            # Translators: Snippet-editor button that opens the variable picker.
            # "&" marks the keyboard mnemonic.
            label=_("Insert &variable..."),
        )
        self.insert_variable_button.Bind(wx.EVT_BUTTON, self._on_insert_variable)
        self.preview_button = wx.Button(
            self.pane,
            # Translators: Snippet-editor button that previews resolved variables.
            # "&" marks the keyboard mnemonic.
            label=_("&Preview..."),
        )
        self.preview_button.Bind(wx.EVT_BUTTON, self._on_preview)
        form_sizer.Add(self.name_label, 0, wx.ALIGN_CENTER_VERTICAL)
        form_sizer.Add(self.name_input, 0, wx.EXPAND)
        form_sizer.Add(self.category_label, 0, wx.ALIGN_CENTER_VERTICAL)
        form_sizer.Add(self.category_input, 0, wx.EXPAND)
        form_sizer.AddSpacer(0)
        form_sizer.Add(self.weight_input, 0, wx.EXPAND)
        form_sizer.Add(self.hotstring_label, 0, wx.ALIGN_CENTER_VERTICAL)
        form_sizer.Add(self.hotstring_input, 0, wx.EXPAND)
        form_sizer.Add(self.content_label, 0, wx.ALIGN_TOP)
        content_sizer = wx.BoxSizer(wx.VERTICAL)
        content_sizer.Add(self.content_input, 1, wx.EXPAND)
        content_action_sizer = wx.BoxSizer(wx.HORIZONTAL)
        content_action_sizer.Add(
            self.insert_variable_button,
            0,
            wx.RIGHT,
            self.FromDIP(8),
        )
        content_action_sizer.Add(self.preview_button)
        content_sizer.Add(content_action_sizer, 0, wx.TOP, self.FromDIP(8))
        form_sizer.Add(content_sizer, 1, wx.EXPAND)
        pane_sizer = wx.BoxSizer(wx.VERTICAL)
        pane_sizer.Add(form_sizer, 1, wx.EXPAND | wx.ALL, self.FromDIP(12))
        self.pane.SetSizer(pane_sizer)

        # Button-Sizer
        btn_sizer = wx.StdDialogButtonSizer()
        # Translators: Snippet-editor button that saves the snippet and closes
        # the dialog. "&" marks the keyboard mnemonic.
        self.save_btn = wx.Button(self, wx.ID_OK, _("&Save"))
        self.save_btn.Bind(wx.EVT_BUTTON, self.save)
        # Translators: Snippet-editor button that discards unsaved changes and
        # closes the dialog. "&" marks the keyboard mnemonic.
        self.cancel_btn = wx.Button(self, wx.ID_CANCEL, _("&Cancel"))
        btn_sizer.AddButton(self.save_btn)
        btn_sizer.AddButton(self.cancel_btn)
        btn_sizer.Realize()
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.save_btn.SetDefault()

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
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)

        if self._snippet is not None:
            self.load()
        self._initial_state = self._current_state()
        self._closing_allowed = False

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
        self.hotstring_input.SetValue(s.hotstring or "")

    def _current_state(self) -> tuple[str, int, int, str, str]:
        """Return all editable values for unsaved-change detection."""
        return (
            self.name_input.GetValue(),
            self.category_input.GetSelection(),
            self.weight_input.GetSelection(),
            self.hotstring_input.GetValue(),
            self.content_input.GetValue(),
        )

    def _has_unsaved_changes(self) -> bool:
        """Return whether an editable value differs from its initial value."""
        return self._current_state() != self._initial_state

    def _confirm_discard_changes(self) -> bool:
        """Ask before discarding changes and return whether closing may proceed."""
        if self._closing_allowed:
            return True
        if not self._has_unsaved_changes():
            return True
        confirmed = utils.confirm_yes_no(
            self,
            # Translators: Confirmation shown when closing the snippet
            # editor would discard changes made since it was opened.
            _("Do you want to discard the unsaved changes?"),
            # Translators: Title of the unsaved-changes confirmation in the
            # snippet editor.
            _("Discard unsaved changes?"),
            warning=True,
        )
        if confirmed:
            self._closing_allowed = True
        return confirmed

    def _on_cancel(self, event: wx.CommandEvent):
        """Close through Cancel only after confirming unsaved changes."""
        if self._closing_allowed:
            return
        if self._confirm_discard_changes():
            self._closing_allowed = True
            self.EndModal(wx.ID_CANCEL)

    def _on_insert_variable(self, event: wx.CommandEvent) -> None:
        """Choose and insert a complete variable at the current selection."""
        with utils.managed_dialog(
            VariablePickerDialog(self, self._variable_suggestions)
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            expression = dialog.get_selected_expression()
        if expression is not None:
            self._insert_expression(expression)

    def _insert_expression(self, expression: str) -> None:
        """Replace the current content selection with one expression."""
        selection_start, selection_end = self.content_input.GetSelection()
        self.content_input.Replace(selection_start, selection_end, expression)
        self.content_input.SetInsertionPoint(selection_start + len(expression))
        self.content_input.SetFocus()

    def _on_preview(self, event: wx.CommandEvent) -> None:
        """Resolve current content and show it without changing the editor."""
        rendered = self._render_variables(self.content_input.GetValue())
        if rendered is None:
            return
        with utils.managed_dialog(
            VariablePreviewDialog(self, rendered.text)
        ) as dialog:
            dialog.ShowModal()

    def _render_variables(self, content: str) -> RenderedSnippet | None:
        """Render content or present one localized variable error."""
        try:
            return self._render_snippet(content)
        except VariableRenderingCancelled:
            return None
        except VariableError as error:
            show_variable_error(self, error)
            return None

    def _variables_are_valid(self, content: str) -> bool:
        """Validate template structure without resolving contextual values."""
        try:
            self._validate_snippet(content)
        except VariableError as error:
            show_variable_error(self, error)
            return False
        return True

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
        if not self._variables_are_valid(snippet_content):
            self.content_input.SetFocus()
            return
        snippet_hotstring = self.hotstring_input.GetValue()
        snippet = datamodel.Snippet(
            name=snippet_name,
            category_id=snippet_category_id,
            weight=snippet_weight,
            content=snippet_content,
            hotstring=snippet_hotstring or None,
        )
        try:
            if self._snippet is None:  # Add new snippet
                self._model.add_snippet(snippet)
            else:  # Edit existing snippet
                snippet.id = self._snippet.id
                self._model.edit_snippet(snippet)
            self._closing_allowed = True
            self.EndModal(wx.OK)
        except datamodel.DataModelError as e:
            wx.MessageBox(
                format_user_error(e),
                _("Validation error"),
                wx.OK | wx.ICON_ERROR,
            )
