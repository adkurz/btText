"""Small UI helpers shared by dialogs and list controls."""

from contextlib import contextmanager

import wx

from i18n import pgettext
from ui import theme


@contextmanager
def managed_dialog(dialog):
    """Destroy a wx dialog reliably after its modal interaction."""
    try:
        yield dialog
    finally:
        dialog.Destroy()


@contextmanager
def frozen(window):
    """Freeze a window temporarily and always thaw it afterwards."""
    window.Freeze()
    try:
        yield window
    finally:
        window.Thaw()


def popup_menu(window, menu) -> None:
    """Show a popup menu and always release its native resources."""
    try:
        window.PopupMenu(menu)
    finally:
        menu.Destroy()


class YesNoConfirmationDialog(wx.Dialog):
    """Show an accessible two-choice confirmation with Escape mapped to No."""
    def __init__(
        self,
        parent,
        message: str,
        title: str,
        *,
        warning: bool = False,
    ):
        """Build a confirmation dialog using native Yes and No buttons."""
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE)

        art_id = wx.ART_WARNING if warning else wx.ART_QUESTION
        icon = wx.StaticBitmap(
            self,
            bitmap=wx.ArtProvider.GetBitmap(
                art_id,
                wx.ART_MESSAGE_BOX,
                self.FromDIP((32, 32)),
            ),
        )
        message_text = wx.StaticText(self, label=message)
        message_text.Wrap(self.FromDIP(480))

        content_sizer = wx.BoxSizer(wx.HORIZONTAL)
        content_sizer.Add(icon, 0, wx.RIGHT | wx.ALIGN_TOP, self.FromDIP(12))
        content_sizer.Add(message_text, 1, wx.ALIGN_CENTER_VERTICAL)

        yes_button = wx.Button(self, wx.ID_YES)
        no_button = wx.Button(self, wx.ID_NO)
        self.no_button = no_button
        button_sizer = wx.StdDialogButtonSizer()
        button_sizer.AddButton(yes_button)
        button_sizer.AddButton(no_button)
        button_sizer.Realize()
        no_button.SetDefault()
        self.SetAffirmativeId(wx.ID_YES)
        self.SetEscapeId(wx.ID_NO)
        yes_button.Bind(wx.EVT_BUTTON, self._on_yes)
        no_button.Bind(wx.EVT_BUTTON, self._on_no)
        self.Bind(wx.EVT_MENU, self._on_no, id=wx.ID_NO)
        self.SetAcceleratorTable(
            wx.AcceleratorTable(
                [wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_ESCAPE, wx.ID_NO)]
            )
        )

        dialog_sizer = wx.BoxSizer(wx.VERTICAL)
        dialog_sizer.Add(
            content_sizer,
            1,
            wx.EXPAND | wx.ALL,
            self.FromDIP(16),
        )
        dialog_sizer.Add(
            button_sizer,
            0,
            wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            self.FromDIP(12),
        )
        self.SetSizerAndFit(dialog_sizer)
        self.SetMinSize(self.FromDIP((420, 180)))
        self.CentreOnParent()
        theme.apply(self)
        self.Bind(wx.EVT_SHOW, self._on_show)

    def _on_show(self, event: wx.ShowEvent):
        """Focus No after the native dialog has become active."""
        event.Skip()
        if event.IsShown():
            wx.CallAfter(self.no_button.SetFocus)

    def _on_yes(self, event: wx.CommandEvent):
        """End the modal interaction with the affirmative result."""
        self.EndModal(wx.ID_YES)

    def _on_no(self, event: wx.CommandEvent):
        """End the modal interaction with No, including for Escape."""
        self.EndModal(wx.ID_NO)


def confirm_yes_no(
    parent,
    message: str,
    title: str,
    *,
    warning: bool = False,
) -> bool:
    """Return whether the user chose Yes in a safe two-choice dialog."""
    with managed_dialog(
        YesNoConfirmationDialog(
            parent,
            message,
            title,
            warning=warning,
        )
    ) as dialog:
        return dialog.ShowModal() == wx.ID_YES


def get_weight_string(weight: int) -> str:
    """Return the human-readable label for a snippet weight."""
    weights = {
        # Translators: Lowest search-ranking weight assigned to a snippet.
        1: pgettext("snippet weight", "Low"),
        # Translators: Medium search-ranking weight assigned to a snippet.
        2: pgettext("snippet weight", "Middle"),
        # Translators: Highest search-ranking weight assigned to a snippet.
        3: pgettext("snippet weight", "High"),
    }
    if not isinstance(weight, int):
        raise TypeError("weight has to be an integer")
    if weight not in weights:
        raise ValueError("Weight has to be an integer between 1 and 3")
    return weights[weight]


def reduce_string(string: str, length: int):
    """Truncate text to a fixed-length preview and append an ellipsis."""
    result = string[:length]
    if len(string) > length:
        result += "..."
    return result
