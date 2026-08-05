"""Accessible dialogs and presentation metadata for snippet variables."""

from dataclasses import dataclass

import wx

from core.builtin_variables import (
    BUILTIN_VARIABLE_FORMATS,
    BUILTIN_VARIABLE_NAMES,
    CONTEXT_VARIABLE_NAMES,
    TEMPORAL_VARIABLE_NAMES,
)
from i18n import _
from ui import theme


@dataclass(frozen=True)
class VariableSuggestion:
    """Describe one complete expression offered by the snippet editor."""

    expression: str
    description: str


def get_builtin_variable_suggestions() -> tuple[VariableSuggestion, ...]:
    """Return localized editor choices for every built-in variable format."""
    value_descriptions = {
        # Translators: Description used in the snippet variable picker.
        "date": _("Current date"),
        # Translators: Description used in the snippet variable picker.
        "time": _("Current time"),
        # Translators: Description used in the snippet variable picker.
        "datetime": _("Current date and time"),
        # Translators: Description used in the snippet variable picker.
        "clipboard": _("Current Unicode text from the Windows clipboard"),
        # Translators: Description used in the snippet variable picker. This is
        # the executable filename, not a possibly private window title.
        "app": _("Executable filename of the target application"),
    }
    suggestions = []
    for name in BUILTIN_VARIABLE_NAMES:
        value_description = value_descriptions[name]
        if name in CONTEXT_VARIABLE_NAMES:
            suggestions.append(
                VariableSuggestion(
                    "{{" + name + "}}",
                    value_description + ".",
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
            )
        )
        if name not in TEMPORAL_VARIABLE_NAMES:
            continue
        for format_name in BUILTIN_VARIABLE_FORMATS:
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
        self._suggestions = suggestions
        # Translators: Label for the list of variables available to insert.
        label = wx.StaticText(self, label=_("&Available variables"))
        self.variable_list = wx.ListBox(
            self,
            choices=[
                f"{suggestion.expression} — {suggestion.description}"
                for suggestion in suggestions
            ],
        )
        # Translators: Accessible name for the snippet variable picker list.
        self.variable_list.SetName(_("Available snippet variables"))
        if suggestions:
            self.variable_list.SetSelection(0)

        button_sizer = wx.StdDialogButtonSizer()
        # Translators: Button that inserts the selected variable expression.
        self.insert_button = wx.Button(self, wx.ID_OK, _("&Insert"))
        # Translators: Button that closes the variable picker without inserting.
        cancel_button = wx.Button(self, wx.ID_CANCEL, _("&Cancel"))
        button_sizer.AddButton(self.insert_button)
        button_sizer.AddButton(cancel_button)
        button_sizer.Realize()
        self.insert_button.Enable(bool(suggestions))
        self.insert_button.SetDefault()
        self.SetAffirmativeId(wx.ID_OK)
        self.SetEscapeId(wx.ID_CANCEL)
        self.variable_list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_activate)

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(label, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(12))
        dialog_sizer.Add(
            self.variable_list,
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
        self.CentreOnParent()
        theme.apply(self)
        self.Bind(wx.EVT_SHOW, self._on_show)

    def get_selected_expression(self) -> str | None:
        """Return the selected complete expression, if one exists."""
        selection = self.variable_list.GetSelection()
        if selection == wx.NOT_FOUND:
            return None
        return self._suggestions[selection].expression

    def _on_activate(self, event: wx.CommandEvent) -> None:
        """Accept a variable activated directly from the list."""
        if self.get_selected_expression() is not None:
            self.EndModal(wx.ID_OK)

    def _on_show(self, event: wx.ShowEvent) -> None:
        """Focus the variable list after the dialog becomes visible."""
        event.Skip()
        if event.IsShown():
            wx.CallAfter(self.variable_list.SetFocus)


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
        self.preview_text = wx.TextCtrl(
            self,
            value=text,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
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
