"""Native view/controller regression checks for committed snippet batches."""

from contextlib import ExitStack
import unittest
from unittest.mock import Mock, patch

import wx

from core.app_settings import AppSettings
from core.datamodel import Category, DataModel, Snippet, SnippetValidationError
from core.events import EventEmitter
from core.variables import RenderedSnippet
from ui.category_tree import CategoryTree
from ui.hotstring_controller import HotstringController
from ui.snippet_list import SnippetList
from ui.transfer import TransferBuffer


class SnippetBatchViewsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def setUp(self):
        self.model = DataModel(EventEmitter(), ":memory:")
        self.source = self.model.add_category(Category("Source"))
        self.target = self.model.add_category(Category("Target"))
        self.snippets = [self.model.add_snippet(Snippet(
            f"Snippet {index:03d}", f"Text {index}", self.source.id,
            weight=index % 3 + 1, hotstring=f";key{index}",
        )) for index in range(100)]
        self.kept = self.model.add_snippet(Snippet("Kept", "Keep", self.source.id,
                                                  hotstring=";keep"))
        self.existing = self.model.add_snippet(Snippet("Existing", "Keep", self.target.id))
        self.hook_patch = patch("ui.hotstring_controller.hotstrings.KeyboardHook")
        self.hook = self.hook_patch.start().return_value
        self.controller = HotstringController(
            Mock(), self.model.ee, self.model, lambda: AppSettings(), Mock(), Mock(),
            lambda text, *args: RenderedSnippet(text),
        )
        self.frame = wx.Frame(None)
        self.buffer = TransferBuffer(self.model)
        self.tree = CategoryTree(self.frame, self.model.ee, self.model, self.buffer)
        self.listing = SnippetList(
            self.frame, self.model.ee, self.model, self.buffer, lambda: True,
            lambda: True, lambda text, md: RenderedSnippet(text), lambda *args: None, (),
        )
        self.select_category(self.source.id)

    def tearDown(self):
        self.tree.Unbind(wx.EVT_TREE_SEL_CHANGED)
        self.frame.Destroy()
        self.app.ProcessPendingEvents()
        self.hook_patch.stop()
        self.model.close()

    def select_category(self, category_id):
        self.tree.focus_id(category_id)
        self.app.Yield()
        self.listing.update(category_id, force=True)

    def row_ids(self):
        return [self.listing.GetItemData(index)
                for index in range(self.listing.GetItemCount())]

    def assert_matches_model(self):
        self.assertEqual(self.row_ids(), [snippet.id for snippet in
                         self.model.get_snippets(self.listing.selected_category_id)])

    def test_copy_refreshes_global_views_once_and_selects_new_rows(self):
        self.select_category(self.target.id)
        self.listing.focus_id(self.existing.id)
        with ExitStack() as stack:
            tree_query = stack.enter_context(patch.object(
                self.model, "get_all_category_summaries", wraps=self.model.get_all_category_summaries))
            hook_query = stack.enter_context(patch.object(
                self.model, "get_hotstring_snippets", wraps=self.model.get_hotstring_snippets))
            sort = stack.enter_context(patch.object(self.listing, "sort", wraps=self.listing.sort))
            self.hook.update.reset_mock()
            with self.assertNoLogs("bttext.events", level="ERROR"):
                copied = self.model.copy_snippets([snippet.id for snippet in self.snippets], self.target.id)
                self.app.Yield()

            tree_query.assert_called_once_with()
            hook_query.assert_called_once_with()
            self.hook.update.assert_called_once()
            sort.assert_called_once_with()
        self.assert_matches_model()
        self.assertEqual(set(self.listing.get_selected_ids()),
                         {self.existing.id, *(snippet.id for snippet in copied)})
        self.assertEqual(self.listing.GetItemData(self.listing.GetFocusedItem()), copied[-1].id)
        self.assertTrue(all(snippet.hotstring is None for snippet in copied))

    def test_move_refreshes_once_and_removes_source_rows_without_losing_selection(self):
        self.listing.focus_id(self.kept.id)
        with (patch.object(self.model, "get_all_category_summaries",
                           wraps=self.model.get_all_category_summaries) as tree_query,
              patch.object(self.model, "get_hotstring_snippets",
                           wraps=self.model.get_hotstring_snippets) as hook_query,
              self.assertNoLogs("bttext.events", level="ERROR")):
            moved = self.model.move_snippets([snippet.id for snippet in self.snippets], self.target.id)
            self.app.Yield()
            tree_query.assert_called_once_with()
            hook_query.assert_called_once_with()
        self.assert_matches_model()
        self.assertEqual(self.row_ids(), [self.kept.id])
        self.assertEqual(self.listing.get_selected_ids(), [self.kept.id])
        self.assertEqual(self.listing.GetItemData(self.listing.GetFocusedItem()), self.kept.id)
        self.assertEqual({snippet.id for snippet in self.hook.update.call_args.args[0].values()},
                         {self.kept.id, *(snippet.id for snippet in moved)})

    def test_move_into_selected_category_selects_all_moved_rows(self):
        self.select_category(self.target.id)
        with self.assertNoLogs("bttext.events", level="ERROR"):
            moved = self.model.move_snippets([snippet.id for snippet in self.snippets], self.target.id)
            self.app.Yield()
        self.assert_matches_model()
        self.assertEqual(set(self.listing.get_selected_ids()), {snippet.id for snippet in moved})
        self.assertEqual(self.listing.GetItemData(self.listing.GetFocusedItem()), moved[-1].id)

    def test_delete_refreshes_once_and_preserves_unrelated_rows_and_hotstrings(self):
        self.listing.focus_id(self.kept.id)
        with (patch.object(self.model, "get_all_category_summaries",
                           wraps=self.model.get_all_category_summaries) as tree_query,
              patch.object(self.model, "get_hotstring_snippets",
                           wraps=self.model.get_hotstring_snippets) as hook_query,
              self.assertNoLogs("bttext.events", level="ERROR")):
            self.model.delete_snippets([snippet.id for snippet in self.snippets])
            self.app.Yield()
            tree_query.assert_called_once_with()
            hook_query.assert_called_once_with()
        self.assert_matches_model()
        self.assertEqual(self.row_ids(), [self.kept.id])
        self.assertEqual(self.listing.get_selected_ids(), [self.kept.id])
        self.assertEqual(self.hook.update.call_args.args[0], {";keep": self.kept})

    def test_failed_batch_leaves_native_views_and_hotstrings_unchanged(self):
        self.model.add_snippet(Snippet(self.snippets[-1].name, "Conflict", self.target.id))
        before = self.row_ids()
        self.hook.update.reset_mock()
        with patch.object(self.model, "get_all_category_summaries",
                          wraps=self.model.get_all_category_summaries) as tree_query:
            with self.assertRaises(SnippetValidationError):
                self.model.move_snippets([snippet.id for snippet in self.snippets], self.target.id)
            self.app.Yield()
            tree_query.assert_not_called()
        self.hook.update.assert_not_called()
        self.assertEqual(self.row_ids(), before)

    def test_single_edits_still_update_and_focus_the_native_row(self):
        snippet = self.model.get_snippet(self.snippets[0].id)
        snippet.name = "Renamed"
        snippet.weight = 3
        with self.assertNoLogs("bttext.events", level="ERROR"):
            self.model.edit_snippet(snippet)
            self.app.Yield()
        self.assert_matches_model()
        self.assertIn(snippet.id, self.listing.get_selected_ids())
        self.assertEqual(self.listing.GetItemData(self.listing.GetFocusedItem()), snippet.id)

    def test_category_deletion_still_clears_a_selected_descendant(self):
        child = self.model.add_category(Category("Child", parent_id=self.source.id))
        self.model.move_snippets([self.snippets[0].id], child.id)
        self.select_category(child.id)
        self.assertEqual(self.row_ids(), [self.snippets[0].id])

        with self.assertNoLogs("bttext.events", level="ERROR"):
            self.model.delete_category(self.source.id)
            self.app.Yield()

        self.assertIsNone(self.listing.selected_category_id)
        self.assertEqual(self.row_ids(), [])
        self.assertEqual(self.hook.update.call_args.args[0], {})


if __name__ == "__main__":
    unittest.main()
