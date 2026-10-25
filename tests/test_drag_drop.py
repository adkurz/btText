"""Native drag format, authorization, and category-drop regression tests."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import wx

from core.datamodel import Category, DataModel, Snippet
from core.events import EventEmitter
from ui.category_tree import CategoryTree
from ui.drag_drop import INTERNAL_DRAG_FORMAT, start_internal_drag
from ui.snippet_list import SnippetList
from ui.transfer import TransferBuffer


class InternalDragTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def setUp(self):
        self.model = DataModel(EventEmitter(), ":memory:")
        self.source = self.model.add_category(Category("Source"))
        self.destination = self.model.add_category(Category("Target"))
        self.snippet = self.model.add_snippet(
            Snippet("Snippet", "Content", self.source.id)
        )
        self.buffer = TransferBuffer(self.model)
        self.frame = wx.Frame(None, size=(500, 400))
        self.tree = CategoryTree(
            self.frame, self.model.ee, self.model, self.buffer
        )
        self.tree.SetSize((480, 350))
        self.target = self.tree.GetDropTarget()

    def tearDown(self):
        self.frame.Destroy()
        self.model.close()

    def _point(self, category_id):
        item = self.tree._items[category_id]
        rect = self.tree.GetBoundingRect(item)
        point = (rect.x + 5, rect.y + rect.height // 2)
        hit, _flags = self.tree.HitTest(point)
        self.assertEqual(self.tree.GetItemData(hit), category_id)
        return point

    def _deliver(self, payload, *, category_id=None, received=True):
        point = self._point(category_id or self.destination.id)
        def receive():
            self.target.GetDataObject().SetData(payload)
            return received
        with patch.object(self.target, "GetData", side_effect=receive):
            return self.target.OnData(*point, wx.DragMove)

    def test_drop_target_offers_no_plain_text_format(self):
        formats = self.target.GetDataObject().GetAllFormats(wx.DataObject.Set)

        self.assertEqual(len(formats), 1)
        self.assertEqual(formats[0].GetId(), INTERNAL_DRAG_FORMAT)
        self.assertNotEqual(formats[0].GetType(), wx.DF_UNICODETEXT)
        self.assertNotEqual(formats[0].GetType(), wx.DF_TEXT)

    def test_foreign_and_malformed_payloads_cannot_move_entities(self):
        pending = self.buffer.value
        with self.buffer.dragging("snippet", self.snippet.id):
            for payload in (
                b"", b"https:123", b"unknown:123", b"snippet:1",
                b"category:1", b"x" * 32, b"\xff" * 32, b"x" * 33,
            ):
                with self.subTest(payload=payload):
                    self.assertEqual(self._deliver(payload), wx.DragNone)
                    self.assertEqual(
                        self.model.get_snippet(self.snippet.id).category_id,
                        self.source.id,
                    )
                    self.assertIsNone(self.model.get_category(self.source.id).parent_id)
                    self.assertTrue(self.buffer.has_drag)
                    self.assertIs(self.buffer.value, pending)

    def test_drop_without_an_active_internal_drag_is_rejected_before_reading(self):
        point = self._point(self.destination.id)
        with patch.object(self.target, "GetData") as receive:
            self.assertFalse(self.target.OnDrop(*point))
            self.assertEqual(
                self.target.OnEnter(*point, wx.DragMove), wx.DragNone
            )
            self.assertEqual(
                self.target.OnData(*point, wx.DragMove), wx.DragNone
            )
        receive.assert_not_called()

    def test_native_source_routes_category_and_snippet_moves_without_staging(self):
        for kind, entity_id in (
            ("category", self.source.id), ("snippet", self.snippet.id)
        ):
            with self.subTest(kind=kind):
                self.buffer.set("snippet", self.snippet.id, copy=True)
                pending = self.buffer.value
                captured = {}
                with patch("ui.drag_drop.wx.DropSource") as source_class:
                    native_source = source_class.return_value
                    native_source.SetData.side_effect = (
                        lambda data: captured.update(data=data)
                    )
                    def drop(_flags):
                        self.assertTrue(self.buffer.has_drag)
                        data = captured["data"]
                        self.assertEqual(data.GetFormat().GetId(), INTERNAL_DRAG_FORMAT)
                        payload = bytes(data.GetData())
                        result = self._deliver(payload)
                        self.assertEqual(self._deliver(payload), wx.DragNone)
                        return result
                    native_source.DoDragDrop.side_effect = drop

                    result = start_internal_drag(
                        self.tree, self.buffer, kind, entity_id
                    )

                self.assertEqual(result, wx.DragMove)
                self.assertFalse(self.buffer.has_drag)
                self.assertIs(self.buffer.value, pending)
                if kind == "category":
                    self.assertEqual(
                        self.model.get_category(entity_id).parent_id,
                        self.destination.id,
                    )
                else:
                    self.assertEqual(
                        self.model.get_snippet(entity_id).category_id,
                        self.destination.id,
                    )

    def test_cancelled_drag_payload_cannot_authorize_a_later_drag(self):
        captured = {}
        with patch("ui.drag_drop.wx.DropSource") as source_class:
            native_source = source_class.return_value
            native_source.SetData.side_effect = (
                lambda data: captured.update(payload=bytes(data.GetData()))
            )
            native_source.DoDragDrop.return_value = wx.DragCancel
            self.assertEqual(
                start_internal_drag(self.tree, self.buffer, "snippet", self.snippet.id),
                wx.DragCancel,
            )
        self.assertFalse(self.buffer.has_drag)
        with self.buffer.dragging("category", self.source.id) as current:
            self.assertEqual(self._deliver(captured["payload"]), wx.DragNone)
            self.assertTrue(self.buffer.has_drag)
            self.assertEqual(self._deliver(current), wx.DragMove)

    def test_native_drag_failure_releases_authorization(self):
        with patch("ui.drag_drop.wx.DropSource") as source_class:
            source_class.return_value.DoDragDrop.side_effect = RuntimeError("failed")
            with self.assertRaisesRegex(RuntimeError, "failed"):
                start_internal_drag(self.tree, self.buffer, "snippet", self.snippet.id)
        self.assertFalse(self.buffer.has_drag)

    def test_failed_or_empty_native_delivery_cannot_reuse_stale_data(self):
        with self.buffer.dragging("snippet", self.snippet.id) as token:
            self.target.GetDataObject().SetData(token)
            point = self._point(self.destination.id)
            for received in (False, True):
                with self.subTest(received=received):
                    with patch.object(self.target, "GetData", return_value=received):
                        self.assertEqual(
                            self.target.OnData(*point, wx.DragMove), wx.DragNone
                        )
                    self.assertTrue(self.buffer.has_drag)
            self.assertEqual(self._deliver(token), wx.DragMove)

    def test_missing_destination_or_refused_native_result_does_not_read_data(self):
        with self.buffer.dragging("snippet", self.snippet.id):
            with patch.object(self.target, "GetData") as receive:
                self.assertEqual(self.target.OnData(-100, -100, wx.DragMove), wx.DragNone)
                point = self._point(self.destination.id)
                for result in (wx.DragNone, wx.DragError, wx.DragCancel, wx.DragLink):
                    self.assertEqual(self.target.OnData(*point, result), wx.DragNone)
                    self.assertEqual(self.target.OnDragOver(*point, result), wx.DragNone)
                self.assertEqual(self.target.OnDragOver(*point, wx.DragCopy), wx.DragMove)
            receive.assert_not_called()

    def test_model_rejection_keeps_category_and_pending_copy_unchanged(self):
        self.buffer.set("snippet", self.snippet.id, copy=True)
        pending = self.buffer.value
        with self.buffer.dragging("category", self.source.id) as token:
            with patch("ui.category_tree.wx.MessageBox") as message:
                self.assertEqual(
                    self._deliver(token, category_id=self.source.id), wx.DragNone
                )
            message.assert_called_once()
            self.assertFalse(self.buffer.has_drag)
        self.assertIsNone(self.model.get_category(self.source.id).parent_id)
        self.assertIs(self.buffer.value, pending)

    def test_empty_tree_placeholder_does_not_start_a_native_drag(self):
        with patch("ui.drag_drop.wx.DropSource") as source:
            self.assertEqual(
                start_internal_drag(self.tree, self.buffer, "category", None),
                wx.DragNone,
            )
        source.assert_not_called()
        self.assertFalse(self.buffer.has_drag)

    def test_both_views_use_the_internal_drag_transport(self):
        view = SimpleNamespace(_transfer_buffer=self.buffer)
        for method, module, kind in (
            (CategoryTree._start_drag, "ui.category_tree", "category"),
            (SnippetList._start_drag, "ui.snippet_list", "snippet"),
        ):
            with self.subTest(kind=kind):
                with patch(module + ".start_internal_drag") as start:
                    method(view, 7)
                start.assert_called_once_with(view, self.buffer, kind, 7)


if __name__ == "__main__":
    unittest.main()
