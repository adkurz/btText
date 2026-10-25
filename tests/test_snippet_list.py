"""Native regression checks for snippet-list sorting."""

from contextlib import ExitStack
import unittest
from unittest.mock import patch

import wx

from core.datamodel import Category, DataModel, Snippet
from core.events import EventEmitter
from core.variables import RenderedSnippet
from ui.snippet_list import SnippetList
from ui.transfer import TransferBuffer


class SnippetListSortingTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.GetApp() or wx.App(False)

    def setUp(self):
        self.model = DataModel(EventEmitter(), ":memory:")
        self.category = self.model.add_category(Category("Sorting"))
        self.frame = wx.Frame(None)
        self.listing = SnippetList(
            self.frame,
            self.model.ee,
            self.model,
            TransferBuffer(self.model),
            lambda: True,
            lambda: True,
            lambda text, markdown: RenderedSnippet(text),
            lambda *args: None,
            (),
        )

    def tearDown(self):
        self.frame.Destroy()
        self.app.ProcessPendingEvents()
        self.model.close()

    def add_snippet(self, name, weight):
        return self.model.add_snippet(
            Snippet(name, "Text", self.category.id, weight=weight)
        )

    def row_ids(self):
        return [
            self.listing.GetItemData(index)
            for index in range(self.listing.GetItemCount())
        ]

    def test_native_sort_prepares_keys_once_and_preserves_selection_and_focus(self):
        low = self.add_snippet("First alphabetically", 1)
        upper = self.add_snippet("Beta", 2)
        lower = self.add_snippet("alpha", 2)
        sharp_s = self.add_snippet("Straße", 2)
        expanded_s = self.add_snippet("STRASSE", 2)
        high = self.add_snippet("Last alphabetically", 3)
        self.listing.update(self.category.id)
        self.listing.focus_id(lower.id)
        self.listing.Select(self.listing.FindItem(-1, high.id))

        # Force a reorder so selection and focus must follow their item data.
        self.listing.SetItem(self.listing.FindItem(-1, upper.id), 2, "3")
        native_sort = self.listing.SortItems
        comparisons = []

        def sort_with_checked_comparator(compare):
            def checked_compare(first, second):
                comparisons.append((first, second))
                return compare(first, second)

            with ExitStack() as stack:
                reads = [
                    stack.enter_context(patch.object(
                        self.listing, name, wraps=getattr(self.listing, name)
                    ))
                    for name in ("FindItem", "GetItemText", "GetItemData")
                ]
                result = native_sort(checked_compare)
                for read in reads:
                    read.assert_not_called()
            self.assertEqual(compare(sharp_s.id, expanded_s.id), 0)
            return result

        count = self.listing.GetItemCount()
        with (
            patch.object(self.listing, "SortItems", side_effect=sort_with_checked_comparator),
            patch.object(self.listing, "GetItemText", wraps=self.listing.GetItemText) as text,
            patch.object(self.listing, "GetItemData", wraps=self.listing.GetItemData) as data,
        ):
            self.listing.sort()
            self.assertEqual(text.call_count, count * 2)
            self.assertEqual(data.call_count, count)

        self.assertTrue(comparisons)
        ids = self.row_ids()
        self.assertEqual(ids[:3], [upper.id, high.id, lower.id])
        self.assertEqual(set(ids[3:5]), {sharp_s.id, expanded_s.id})
        self.assertEqual(ids[-1], low.id)
        self.assertEqual(set(self.listing.get_selected_ids()), {lower.id, high.id})
        self.assertEqual(
            self.listing.GetItemData(self.listing.GetFocusedItem()), lower.id
        )

    def test_sort_keys_follow_edits_additions_deletions_and_category_reloads(self):
        alpha = self.add_snippet("Alpha", 2)
        beta = self.add_snippet("Beta", 3)
        self.listing.update(self.category.id)
        self.assertEqual(self.row_ids(), [beta.id, alpha.id])

        with self.assertNoLogs("bttext.events", level="ERROR"):
            alpha.name = "Aardvark"
            alpha.weight = 3
            self.model.edit_snippet(alpha)
            self.assertEqual(self.row_ids(), [alpha.id, beta.id])

            beta.name = "aardwolf"
            self.model.edit_snippet(beta)
            self.assertEqual(self.row_ids(), [alpha.id, beta.id])

            new = self.add_snippet("Aaron", 3)
            self.assertEqual(self.row_ids(), [alpha.id, beta.id, new.id])
            self.model.delete_snippets([alpha.id])
            self.listing.sort()
            self.assertEqual(self.row_ids(), [beta.id, new.id])

        self.listing.update(None)
        self.listing.sort()
        self.assertEqual(self.row_ids(), [])
        self.listing.update(self.category.id)
        self.assertEqual(self.row_ids(), [beta.id, new.id])


if __name__ == "__main__":
    unittest.main()
