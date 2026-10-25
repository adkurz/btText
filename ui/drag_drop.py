"""Native drag transport for active, application-local entity moves."""

import wx

from ui.transfer import DRAG_TOKEN_BYTES, TransferBuffer, TransferKind


INTERNAL_DRAG_FORMAT = "btText.InternalTransfer"


def start_internal_drag(
    window: wx.Window,
    buffer: TransferBuffer,
    kind: TransferKind,
    entity_id: int | None,
) -> wx.DragResult:
    """Publish an opaque drag token instead of an entity ID as plain text."""
    if entity_id is None:
        return wx.DragNone
    with buffer.dragging(kind, entity_id) as token:
        data = wx.CustomDataObject(INTERNAL_DRAG_FORMAT)
        data.SetData(token)
        source = wx.DropSource(window)
        source.SetData(data)
        return source.DoDragDrop(wx.Drag_AllowMove)


class CategoryDropTarget(wx.DropTarget):
    """Accept only a live drag issued through the tree's shared buffer."""

    def __init__(self, tree):
        super().__init__()
        self._tree = tree
        self._data = wx.CustomDataObject(INTERNAL_DRAG_FORMAT)
        self.SetDataObject(self._data)

    def OnEnter(self, x, y, defResult):
        return self.OnDragOver(x, y, defResult)

    def OnDragOver(self, x, y, defResult):
        if defResult not in (wx.DragCopy, wx.DragMove) or not self.OnDrop(x, y):
            return wx.DragNone
        return wx.DragMove

    def OnDrop(self, x, y):
        if not self._tree._transfer_buffer.has_drag:
            return False
        item, _flags = self._tree.HitTest((x, y))
        return item.IsOk()

    def OnData(self, x, y, defResult):
        """Validate and consume the token before requesting a model mutation."""
        if defResult not in (wx.DragCopy, wx.DragMove) or not self.OnDrop(x, y):
            return wx.DragNone
        # Do not reuse data retained from a previous native drop.
        self._data.SetData(b"")
        if not self.GetData() or self._data.GetSize() != DRAG_TOKEN_BYTES:
            return wx.DragNone
        transfer = self._tree._transfer_buffer.take_drag(bytes(self._data.GetData()))
        if transfer is None:
            return wx.DragNone
        item, _flags = self._tree.HitTest((x, y))
        if not item.IsOk():
            return wx.DragNone
        category_id = self._tree.GetItemData(item)
        if not self._tree.transfer_to(
            transfer.kind, transfer.entity_ids, category_id, copy=False
        ):
            return wx.DragNone
        return wx.DragMove
