import pymitter
import wx

import datamodel


class BaseList(wx.ListView):
    def __init__(self, parent, ee: pymitter.EventEmitter, model: datamodel.DataModel):
        super().__init__(
            parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_SORT_ASCENDING
        )
        self._ee = ee
        self._model = model

    def get_selected_id(self):
        index = self.GetFirstSelected()
        return self.GetItemData(index) if index != wx.NOT_FOUND else None

    def focus_id(self, id: int, select: bool = True):
        index = self.FindItem(-1, id)
        if index == wx.NOT_FOUND:
            return False
        self.Focus(index)
        if select:
            self.Select(index)
        return True

    def sort(self):
        self.SortItems(self._sort_compare)

    def _sort_compare(self, item1: int, item2: int):
        name1: str = self.GetItemText(self.FindItem(-1, item1))
        name2: str = self.GetItemText(self.FindItem(-1, item2))
        name1 = name1.casefold()
        name2 = name2.casefold()
        return (name1 > name2) - (name1 < name2)
