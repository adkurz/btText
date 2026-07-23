"""Reusable wxPython form validators."""

import wx


class NonEmptyValidator(wx.Validator):
    """Reject text controls whose value is empty or whitespace-only."""
    def __init__(self):
        """Create a validator for one text control."""
        super().__init__()

    def Clone(self):
        """Return the independent validator instance required by wxPython."""
        return NonEmptyValidator()

    def Validate(self, parent):
        """Show an error and focus the control when its value is blank."""
        input = self.GetWindow()
        text = input.GetValue().strip() # type: ignore
        if not text:
            wx.MessageBox('The input field must not be empty!', 'Validation error', wx.OK | wx.ICON_ERROR)
            input.SetFocus()
            input.Refresh()
            return False
        else:
            input.Refresh()
            return True

    def TransferToWindow(self):
        """Report success because the validator owns no external data."""
        return True  

    def TransferFromWindow(self):
        """Report success because the validator owns no external data."""
        return True
