"""Tests for shared category and snippet transfer orchestration."""

import unittest
from unittest.mock import Mock

from core import datamodel
from ui.transfer import TransferBuffer, TransferService


class TransferServiceTestCase(unittest.TestCase):
    """Verify model routing and copy/cut buffer lifecycle."""

    def setUp(self):
        self.model = Mock()
        self.buffer = TransferBuffer()
        self.service = TransferService(self.model, self.buffer)

    def test_stage_normalizes_one_entity_id(self):
        transfer = self.service.stage("category", 7, copy=True)

        self.assertIs(transfer, self.service.pending)
        self.assertEqual(transfer.entity_ids, (7,))
        self.assertTrue(transfer.copy)

    def test_category_copy_returns_model_result_and_remains_staged(self):
        category = datamodel.Category("Copied", id=9, parent_id=3)
        self.model.copy_category.return_value = category
        transfer = self.service.stage("category", 7, copy=True)

        result = self.service.apply_pending(3)

        self.model.copy_category.assert_called_once_with(7, 3)
        self.assertIs(result.transfer, transfer)
        self.assertIs(result.category, category)
        self.assertEqual(result.snippets, ())
        self.assertIs(self.service.pending, transfer)

    def test_category_cut_moves_and_clears_successful_transfer(self):
        category = datamodel.Category("Moved", id=7, parent_id=None)
        self.model.move_category.return_value = category
        self.service.stage("category", 7, copy=False)

        result = self.service.apply_pending(None)

        self.model.move_category.assert_called_once_with(7, None)
        self.assertIs(result.category, category)
        self.assertIsNone(self.service.pending)

    def test_snippet_copy_returns_all_model_results(self):
        snippets = [
            datamodel.Snippet("One", "1", 4, id=10),
            datamodel.Snippet("Two", "2", 4, id=11),
        ]
        self.model.copy_snippets.return_value = snippets
        self.service.stage("snippet", (1, 2), copy=True)

        result = self.service.apply_pending(4)

        self.model.copy_snippets.assert_called_once_with((1, 2), 4)
        self.assertEqual(result.snippets, tuple(snippets))
        self.assertIsNone(result.category)

    def test_snippet_cut_failure_keeps_transfer_for_retry(self):
        error = datamodel.DataModelError("failed", "failed")
        self.model.move_snippets.side_effect = error
        transfer = self.service.stage("snippet", (1, 2), copy=False)

        with self.assertRaises(datamodel.DataModelError):
            self.service.apply_pending(4)

        self.assertIs(self.service.pending, transfer)

    def test_apply_without_pending_transfer_does_nothing(self):
        self.assertIsNone(self.service.apply_pending(4))
        self.model.assert_not_called()

    def test_invalid_staged_kind_is_rejected_without_replacing_pending_transfer(self):
        pending = self.service.stage("snippet", 2, copy=True)

        with self.assertRaisesRegex(
            ValueError,
            "Unsupported transfer kind: 'unknown'",
        ):
            self.service.stage("unknown", 7, copy=False)

        self.assertIs(self.service.pending, pending)
        self.model.assert_not_called()

    def test_invalid_unstaged_kind_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "Unsupported transfer kind: 'unknown'",
        ):
            self.service.execute("unknown", 7, 4, copy=False)

        self.assertIsNone(self.service.pending)
        self.model.assert_not_called()

    def test_unstaged_drag_move_does_not_replace_pending_transfer(self):
        category = datamodel.Category("Moved", id=7, parent_id=4)
        self.model.move_category.return_value = category
        pending = self.service.stage("snippet", 2, copy=True)

        result = self.service.execute("category", 7, 4, copy=False)

        self.model.move_category.assert_called_once_with(7, 4)
        self.assertIs(result.category, category)
        self.assertIs(self.service.pending, pending)


if __name__ == "__main__":
    unittest.main()
