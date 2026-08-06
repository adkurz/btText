"""Accessible dialogs and presentation metadata for snippet variables."""

from dataclasses import dataclass

import wx

from core.builtin_variables import (
    BUILTIN_VARIABLE_CATALOG,
    VariableDescription,
    VariableEditorKind,
)
from i18n import _
from platform_support import windows
from ui import theme
from ui.controls import FocusableReadOnlyTextCtrl


@dataclass(frozen=True)
class VariableSuggestion:
    """Describe one complete expression offered by the snippet editor."""

    expression: str
    description: str
    variable_description: str | None = None
    editor_kind: VariableEditorKind = VariableEditorKind.PLAIN


def _get_variable_description(description: VariableDescription) -> str:
    """Localize one stable description identifier from the core catalog."""
    descriptions = {
        # Translators: Description used in the snippet variable picker.
        VariableDescription.DATE: _("Current date"),
        # Translators: Description used in the snippet variable picker.
        VariableDescription.TIME: _("Current time"),
        # Translators: Description used in the snippet variable picker.
        VariableDescription.DATETIME: _("Current date and time"),
        # Translators: Description used in the snippet variable picker.
        VariableDescription.CLIPBOARD: _(
            "Current Unicode text from the Windows clipboard"
        ),
        # Translators: Description used in the snippet variable picker. This is
        # the executable filename, not a possibly private window title.
        VariableDescription.APPLICATION: _(
            "Executable filename of the target application"
        ),
        # Translators: Description used in the snippet variable picker.
        VariableDescription.INPUT: _("Text requested during insertion"),
        # Translators: Description used in the snippet variable picker.
        VariableDescription.CURSOR: _("Final cursor position after insertion"),
    }
    return descriptions[description]


def get_builtin_variable_suggestions() -> tuple[VariableSuggestion, ...]:
    """Return localized editor choices for every built-in variable format."""
    suggestions = []
    for variable in BUILTIN_VARIABLE_CATALOG:
        name = variable.definition.name
        value_description = _get_variable_description(variable.description)
        if variable.editor_kind is VariableEditorKind.PLAIN:
            suggestions.append(
                VariableSuggestion(
                    "{{" + name + "}}",
                    value_description + ".",
                    value_description,
                    variable.editor_kind,
                )
            )
            continue
        if variable.editor_kind is VariableEditorKind.INPUT_LABEL:
            placeholder = variable.editor_placeholder
            if placeholder is None:
                raise ValueError(
                    f"Variable {name!r} requires an editor placeholder."
                )
            suggestions.append(
                VariableSuggestion(
                    "{{" + name + ":" + placeholder + "}}",
                    # Translators: Description for the editable placeholder in
                    # an interactive input variable expression.
                    _("Replace 'Prompt' with the requested value's label."),
                    value_description,
                    variable.editor_kind,
                )
            )
            continue
        suggestions.append(
            VariableSuggestion(
                "{{" + name + "}}",
                # Translators: Description for a variable without an explicit
                # format. {value} is a localized date/time value description.
                _("{value} using the default localized short format.").format(
                    value=value_description
                ),
                value_description,
                variable.editor_kind,
            )
        )
        for format_name in variable.editor_options:
            if format_name == "iso":
                continue
            suggestions.append(
                VariableSuggestion(
                    "{{" + name + ":" + format_name + "}}",
                    # Translators: Description for a localized date/time
                    # variable. {value} is its value type; {format} is a
                    # language-independent technical format name.
                    _("{value} using the localized '{format}' format.").format(
                        value=value_description,
                        format=format_name,
                    ),
                    value_description,
                    variable.editor_kind,
                )
            )
        suggestions.append(
            VariableSuggestion(
                "{{" + name + ":iso}}",
                # Translators: Description for a language-independent date/time
                # variable. {value} is a localized value description.
                _("{value} using the language-independent ISO format.").format(
                    value=value_description
                ),
                value_description,
                variable.editor_kind,
            )
        )
    return tuple(suggestions)


class VariablePickerDialog(wx.Dialog):
    """Let the user choose one complete variable expression."""

    def __init__(
        self,
        parent: wx.Window,
        suggestions: tuple[VariableSuggestion, ...],
    ) -> None:
        super().__init__(
            parent,
            # Translators: Window title for choosing a snippet variable.
            title=_("Insert variable"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._groups = self._group_suggestions(suggestions)
        self._visible_suggestions: tuple[VariableSuggestion, ...] = ()
        self._visible_name: str | None = None
        self._visible_editor_kind = VariableEditorKind.PLAIN
        # Translators: Label for the list of variables available to insert.
        label = wx.StaticText(self, label=_("&Available variables"))
        self.variable_list = wx.ListBox(
            self,
            choices=[
                f"{{{{{name}}}}} — "
                f"{group[0].variable_description or group[0].description}"
                for name, group in self._groups
            ],
        )
        # Translators: Accessible name for the snippet variable picker list.
        self.variable_list.SetName(_("Available snippet variables"))
        if self._groups:
            self.variable_list.SetSelection(0)

        self.settings_panel = wx.Panel(self)
        settings_sizer = wx.BoxSizer(wx.VERTICAL)
        self.settings_label = wx.StaticText(
            self.settings_panel,
            # Translators: Label for optional variable formats or settings.
            label=_("Possible &formats or settings"),
        )
        self.settings_list = wx.ListBox(self.settings_panel)
        self.settings_list.SetName(
            # Translators: Accessible name for optional variable
            # formats/settings.
            _("Available variable formats or settings")
        )
        # Translators: Label for the prompt stored in an interactive input
        # variable. "&" marks the keyboard mnemonic.
        self.input_label = wx.StaticText(self.settings_panel, label=_("&Prompt"))
        self.input_text = wx.TextCtrl(self.settings_panel)
        # Translators: Accessible name for the editable prompt of {{input}}.
        self.input_text.SetName(_("Interactive variable prompt"))
        settings_sizer.Add(self.settings_label, 0, wx.BOTTOM, self.FromDIP(6))
        settings_sizer.Add(self.settings_list, 1, wx.EXPAND)
        settings_sizer.Add(self.input_label, 0, wx.BOTTOM, self.FromDIP(6))
        settings_sizer.Add(self.input_text, 0, wx.EXPAND)
        self.settings_panel.SetSizer(settings_sizer)

        button_sizer = wx.StdDialogButtonSizer()
        # Translators: Button that inserts the selected variable expression.
        self.insert_button = wx.Button(self, wx.ID_OK, _("&Insert"))
        # Translators: Button that closes the variable picker without inserting.
        cancel_button = wx.Button(self, wx.ID_CANCEL, _("&Cancel"))
        button_sizer.AddButton(self.insert_button)
        button_sizer.AddButton(cancel_button)
        button_sizer.Realize()
        self.insert_button.Enable(bool(self._groups))
        self.insert_button.SetDefault()
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.variable_list.Bind(wx.EVT_LISTBOX, self._on_variable_selected)
        self.variable_list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_variable_activated)
        self.settings_list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_activate)
        self.input_text.Bind(wx.EVT_TEXT, self._on_input_changed)

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(label, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(12))
        choices_sizer = wx.BoxSizer(wx.HORIZONTAL)
        choices_sizer.Add(
            self.variable_list,
            1,
            wx.EXPAND | wx.RIGHT,
            self.FromDIP(12),
        )
        choices_sizer.Add(self.settings_panel, 1, wx.EXPAND)
        dialog_sizer.Add(
            choices_sizer,
            1,
            wx.EXPAND | wx.ALL,
            self.FromDIP(12),
        )
        dialog_sizer.Add(
            button_sizer,
            0,
            wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            self.FromDIP(12),
        )
        self.SetSizer(dialog_sizer)
        self.SetMinSize(self.FromDIP((620, 360)))
        self.SetSize(self.FromDIP((760, 520)))
        self._update_settings()
        self.CentreOnParent()
        theme.apply(self)
        self.Bind(wx.EVT_SHOW, self._on_show)

    def get_selected_expression(self) -> str | None:
        """Return the selected complete expression, if one exists."""
        variable_selection = self.variable_list.GetSelection()
        if variable_selection == wx.NOT_FOUND or not self._visible_suggestions:
            return None
        if self._visible_editor_kind is VariableEditorKind.INPUT_LABEL:
            label = self.input_text.GetValue()
            if not self._input_label_is_valid(label):
                return None
            return "{{input:" + label + "}}"
        if len(self._visible_suggestions) == 1:
            return self._visible_suggestions[0].expression
        setting_selection = self.settings_list.GetSelection()
        if setting_selection == wx.NOT_FOUND:
            return None
        return self._visible_suggestions[setting_selection].expression

    @staticmethod
    def _group_suggestions(
        suggestions: tuple[VariableSuggestion, ...],
    ) -> tuple[tuple[str, tuple[VariableSuggestion, ...]], ...]:
        """Group complete expressions by their technical variable name."""
        groups: dict[str, list[VariableSuggestion]] = {}
        for suggestion in suggestions:
            content = suggestion.expression.removeprefix("{{").removesuffix("}}")
            name = content.partition(":")[0]
            groups.setdefault(name, []).append(suggestion)
        return tuple((name, tuple(group)) for name, group in groups.items())

    @staticmethod
    def _setting_label(suggestion: VariableSuggestion) -> str:
        content = suggestion.expression.removeprefix("{{").removesuffix("}}")
        _name, separator, setting = content.partition(":")
        if not separator:
            # Translators: Default choice for a variable with optional formats.
            setting = _("Default")
        return f"{setting} — {suggestion.description}"

    def _update_settings(self) -> None:
        """Show the settings belonging to the selected variable, if any."""
        selection = self.variable_list.GetSelection()
        if selection == wx.NOT_FOUND:
            self._visible_name = None
            self._visible_editor_kind = VariableEditorKind.PLAIN
            self._visible_suggestions = ()
        else:
            self._visible_name, self._visible_suggestions = self._groups[selection]
            self._visible_editor_kind = self._visible_suggestions[0].editor_kind
        has_custom_input = (
            self._visible_editor_kind is VariableEditorKind.INPUT_LABEL
        )
        has_settings = len(self._visible_suggestions) > 1
        self.settings_list.Set(
            [self._setting_label(item) for item in self._visible_suggestions]
            if has_settings
            else []
        )
        if has_settings:
            self.settings_list.SetSelection(0)
        self.settings_list.Show(has_settings)
        self.input_label.Show(has_custom_input)
        self.input_text.Show(has_custom_input)
        self.settings_panel.Show(has_settings or has_custom_input)
        self._update_insert_button()
        self.Layout()

    @staticmethod
    def _input_label_is_valid(label: str) -> bool:
        """Return whether a label fits the variable expression grammar."""
        return (
            bool(label.strip())
            and ":" not in label
            and "{{" not in label
            and "}}" not in label
        )

    def _update_insert_button(self) -> None:
        """Enable insertion only when the current expression is complete."""
        self.insert_button.Enable(self.get_selected_expression() is not None)

    def _on_input_changed(self, event: wx.CommandEvent) -> None:
        self._update_insert_button()

    def _on_variable_selected(self, event: wx.CommandEvent) -> None:
        self._update_settings()

    def _on_variable_activated(self, event: wx.CommandEvent) -> None:
        """Insert a setting-free variable or move to its settings list."""
        self._update_settings()
        if len(self._visible_suggestions) == 1:
            if self._visible_editor_kind is VariableEditorKind.INPUT_LABEL:
                self.input_text.SetFocus()
            else:
                self.EndModal(wx.ID_OK)
        else:
            self.settings_list.SetFocus()

    def _on_activate(self, event: wx.CommandEvent) -> None:
        """Accept a variable activated directly from the list."""
        if self.get_selected_expression() is not None:
            self.EndModal(wx.ID_OK)

    def _on_show(self, event: wx.ShowEvent) -> None:
        """Focus the variable list after the dialog becomes visible."""
        event.Skip()
        if event.IsShown():
            wx.CallAfter(self.variable_list.SetFocus)


class InteractiveVariablesDialog(wx.Dialog):
    """Collect every interactive value required by one rendering."""

    def __init__(self, parent: wx.Window | None, labels: tuple[str, ...]) -> None:
        if not labels:
            raise ValueError("At least one interactive variable label is required.")
        super().__init__(
            parent,
            # Translators: Window title for entering all interactive snippet
            # variable values in one dialog.
            title=_("Enter variable values"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._labels = labels
        self._inputs: dict[str, wx.TextCtrl] = {}

        instructions = wx.StaticText(
            self,
            # Translators: Instructions above interactive snippet variable
            # fields.
            label=_("Enter the values required by this snippet."),
        )
        fields_panel = wx.ScrolledWindow(self)
        fields_panel.SetScrollRate(0, self.FromDIP(10))
        fields_sizer = wx.FlexGridSizer(
            cols=2,
            vgap=self.FromDIP(10),
            hgap=self.FromDIP(12),
        )
        fields_sizer.AddGrowableCol(1, 1)
        for label in labels:
            mnemonic_marker = chr(38)
            display_label = label.replace(
                mnemonic_marker,
                mnemonic_marker * 2,
            )
            label_control = wx.StaticText(
                fields_panel,
                label=display_label,
            )
            value_input = wx.TextCtrl(fields_panel)
            value_input.SetName(label)
            fields_sizer.Add(label_control, 0, wx.ALIGN_CENTER_VERTICAL)
            fields_sizer.Add(value_input, 0, wx.EXPAND)
            self._inputs[label] = value_input
        fields_panel.SetSizer(fields_sizer)

        button_sizer = wx.StdDialogButtonSizer()
        ok_button = wx.Button(self, wx.ID_OK)
        cancel_button = wx.Button(self, wx.ID_CANCEL)
        button_sizer.AddButton(ok_button)
        button_sizer.AddButton(cancel_button)
        button_sizer.Realize()
        ok_button.SetDefault()
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(
            instructions,
            0,
            wx.LEFT | wx.RIGHT | wx.TOP,
            self.FromDIP(12),
        )
        dialog_sizer.Add(
            fields_panel,
            1,
            wx.EXPAND | wx.ALL,
            self.FromDIP(12),
        )
        dialog_sizer.Add(
            button_sizer,
            0,
            wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            self.FromDIP(12),
        )
        self.SetSizer(dialog_sizer)
        self.SetMinSize(self.FromDIP((480, 280)))
        self.SetSize(self.FromDIP((620, 420)))
        self.CentreOnParent()
        theme.apply(self)
        self.Bind(wx.EVT_SHOW, self._on_show)

    def get_values(self) -> dict[str, str]:
        """Return every entered value keyed by its technical label."""
        return {
            label: self._inputs[label].GetValue()
            for label in self._labels
        }

    def _on_show(self, event: wx.ShowEvent) -> None:
        """Focus the first value field when the dialog is displayed."""
        event.Skip()
        if event.IsShown():
            wx.CallAfter(self._activate_and_focus_first_input)

    def _activate_and_focus_first_input(self) -> None:
        """Bring the dialog forward before focusing its first value field."""
        windows.activate_window(self.GetHandle())
        self.Raise()
        self._inputs[self._labels[0]].SetFocus()


class VariablePreviewDialog(wx.Dialog):
    """Display rendered snippet text in a focusable read-only control."""

    def __init__(self, parent: wx.Window, text: str) -> None:
        super().__init__(
            parent,
            # Translators: Window title for rendered snippet variable output.
            title=_("Variable preview"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        # Translators: Label for the rendered snippet text in the preview.
        label = wx.StaticText(self, label=_("Resolved &text"))
        self.preview_text = FocusableReadOnlyTextCtrl(
            self,
            value=text,
            style=wx.TE_MULTILINE | wx.TE_RICH2,
        )
        # Translators: Accessible name for rendered snippet preview text.
        self.preview_text.SetName(_("Resolved snippet text"))
        close_button = wx.Button(self, wx.ID_CLOSE)
        close_button.SetDefault()
        close_button.Bind(wx.EVT_BUTTON, self._on_close)
        self.SetEscapeId(wx.ID_CLOSE)

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(label, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(12))
        dialog_sizer.Add(
            self.preview_text,
            1,
            wx.EXPAND | wx.ALL,
            self.FromDIP(12),
        )
        dialog_sizer.Add(
            close_button,
            0,
            wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            self.FromDIP(12),
        )
        self.SetSizer(dialog_sizer)
        self.SetMinSize(self.FromDIP((560, 360)))
        self.SetSize(self.FromDIP((720, 500)))
        self.CentreOnParent()
        theme.apply(self)
        self.Bind(wx.EVT_SHOW, self._on_show)

    def _on_close(self, event: wx.CommandEvent) -> None:
        self.EndModal(wx.ID_CLOSE)

    def _on_show(self, event: wx.ShowEvent) -> None:
        """Focus the preview text so keyboard users can review and copy it."""
        event.Skip()
        if event.IsShown():
            wx.CallAfter(self.preview_text.SetFocus)
