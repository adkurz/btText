import wx


class NonEmptyValidator(wx.Validator):
    def __init__(self):
        super().__init__()

    def Clone(self):
        return NonEmptyValidator()

    def Validate(self, parent):
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
        return True  

    def TransferFromWindow(self):
        return True  