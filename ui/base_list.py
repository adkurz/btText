"""Shared identity-based selection and sorting for list controls."""

import pymitter
import wx

import datamodel


class BaseList(wx.ListView):
    """List view whose item data stores stable model identifiers."""
    def __init__(
        self,
        parent,
        ee: pymitter.EventEmitter,
        model: datamodel.DataModel,
        multiple_selection: bool = False,
    ):
        """Initialize a report-style list backed by the shared model."""
        style = wx.LC_REPORT | wx.LC_SORT_ASCENDING
        if not multiple_selection:
            style |= wx.LC_SINGLE_SEL
        super().__init__(parent, style=style)
        self._ee = ee
        self._model = model

    def get_selected_id(self):
        """Return the model ID of the selected row, if any."""
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

    def focus_id(self, id: int, select: bool = True):
        """Focus and optionally select the row carrying a model ID."""
        index = self.FindItem(-1, id)
        if index == wx.NOT_FOUND:
            return False
        self.Focus(index)
        if select:
            self.Select(index)
        return True

    def sort(self):
        """Sort rows using the control's comparison callback."""
        self.SortItems(self._sort_compare)

    def _sort_compare(self, item1: int, item2: int):
        """Compare item IDs by their case-insensitive name column."""
        name1: str = self.GetItemText(self.FindItem(-1, item1))
        name2: str = self.GetItemText(self.FindItem(-1, item2))
        name1 = name1.casefold()
        name2 = name2.casefold()
        return (name1 > name2) - (name1 < name2)
