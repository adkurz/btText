"""Tests for shared category and snippet transfer orchestration."""

import unittest
from unittest.mock import Mock, patch

from core import datamodel
from core.events import EventEmitter
from ui.transfer import TransferBuffer, TransferService


class TransferServiceTestCase(unittest.TestCase):
    """Verify model routing and copy/cut buffer lifecycle."""

    def setUp(self):
        self.model = Mock()
        self.buffer = TransferBuffer(self.model)
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


class TransferDeletionTestCase(unittest.TestCase):
    """Reject deleted sources even after SQLite reuses their numeric IDs."""

    def _create_service(self):
        model = datamodel.DataModel(EventEmitter(), ":memory:")
        self.addCleanup(model.close)
        buffer = TransferBuffer(model)
        return model, buffer, TransferService(model, buffer)

    def test_deleted_category_source_cannot_transfer_a_reused_id(self):
        for copy in (True, False):
            with self.subTest(copy=copy):
                model, buffer, service = self._create_service()
                destination = model.add_category(datamodel.Category("Destination"))
                source = model.add_category(datamodel.Category("Source"))
                service.stage("category", source.id, copy)

                model.delete_category(source.id)
                replacement = model.add_category(datamodel.Category("Replacement"))

                self.assertEqual(replacement.id, source.id)
                self.assertIsNone(buffer.value)
                self.assertIsNone(service.apply_pending(destination.id))
                self.assertIsNone(model.get_category(replacement.id).parent_id)
                self.assertEqual(len(tuple(model.get_categories())), 2)

    def test_deleted_descendant_source_cannot_transfer_a_reused_id(self):
        for copy in (True, False):
            with self.subTest(copy=copy):
                model, buffer, service = self._create_service()
                destination = model.add_category(datamodel.Category("Destination"))
                root = model.add_category(datamodel.Category("Root"))
                child = model.add_category(
                    datamodel.Category("Child", parent_id=root.id)
                )
                source = model.add_category(
                    datamodel.Category("Source", parent_id=child.id)
                )
                service.stage("category", source.id, copy)

                model.delete_category(root.id)
                for name in ("Replacement root", "Replacement child", "Replacement"):
                    replacement = model.add_category(datamodel.Category(name))

                self.assertEqual(replacement.id, source.id)
                self.assertIsNone(buffer.value)
                self.assertIsNone(service.apply_pending(destination.id))
                self.assertIsNone(model.get_category(replacement.id).parent_id)

    def test_category_deletion_invalidates_entire_mixed_snippet_transfer(self):
        for copy in (True, False):
            with self.subTest(copy=copy):
                model, buffer, service = self._create_service()
                destination = model.add_category(datamodel.Category("Destination"))
                surviving = model.add_snippet(
                    datamodel.Snippet("Surviving", "Keep", destination.id)
                )
                root = model.add_category(datamodel.Category("Root"))
                child = model.add_category(
                    datamodel.Category("Child", parent_id=root.id)
                )
                deleted = model.add_snippet(
                    datamodel.Snippet("Deleted", "Old", child.id)
                )
                service.stage("snippet", (surviving.id, deleted.id), copy)

                model.delete_category(root.id)
                replacement_category = model.add_category(
                    datamodel.Category("Replacement category")
                )
                replacement = model.add_snippet(
                    datamodel.Snippet("Replacement", "New", replacement_category.id)
                )

                self.assertEqual(replacement.id, deleted.id)
                self.assertIsNone(buffer.value)
                self.assertIsNone(service.apply_pending(destination.id))
                self.assertEqual(
                    model.get_snippet(replacement.id).category_id,
                    replacement_category.id,
                )
                self.assertEqual(
                    model.get_snippet(surviving.id).category_id, destination.id
                )
                self.assertEqual(len(tuple(model.get_snippets(destination.id))), 1)

    def test_direct_snippet_deletion_invalidates_transfer_before_id_reuse(self):
        for copy in (True, False):
            with self.subTest(copy=copy):
                model, buffer, service = self._create_service()
                source_category = model.add_category(datamodel.Category("Source"))
                destination = model.add_category(datamodel.Category("Destination"))
                source = model.add_snippet(
                    datamodel.Snippet("Source", "Old", source_category.id)
                )
                service.stage("snippet", source.id, copy)

                model.delete_snippets([source.id])
                replacement = model.add_snippet(
                    datamodel.Snippet("Replacement", "New", source_category.id)
                )

                self.assertEqual(replacement.id, source.id)
                self.assertIsNone(buffer.value)
                self.assertIsNone(service.apply_pending(destination.id))
                self.assertEqual(
                    model.get_snippet(replacement.id).category_id, source_category.id
                )
                self.assertEqual(tuple(model.get_snippets(destination.id)), ())

    def test_unrelated_deletions_preserve_pending_transfers(self):
        for kind in ("category", "snippet"):
            for copy in (True, False):
                with self.subTest(kind=kind, copy=copy):
                    model, buffer, service = self._create_service()
                    destination = model.add_category(datamodel.Category("Destination"))
                    source_category = model.add_category(datamodel.Category("Source"))
                    source = source_category
                    if kind == "snippet":
                        source = model.add_snippet(
                            datamodel.Snippet("Source snippet", "Keep", source_category.id)
                        )
                    pending = service.stage(kind, source.id, copy)
                    unrelated = model.add_category(datamodel.Category("Unrelated"))
                    unrelated_snippet = model.add_snippet(
                        datamodel.Snippet("Unrelated", "Delete", unrelated.id)
                    )

                    model.delete_snippets([unrelated_snippet.id])
                    model.delete_category(unrelated.id)

                    self.assertIs(buffer.value, pending)
                    result = service.apply_pending(destination.id)
                    self.assertIsNotNone(result)
                    if kind == "category":
                        self.assertEqual(result.category.parent_id, destination.id)
                    else:
                        self.assertEqual(result.snippets[0].category_id, destination.id)

    def test_failed_category_deletion_preserves_pending_transfer(self):
        model, buffer, service = self._create_service()
        source = model.add_category(datamodel.Category("Source"))
        pending = service.stage("category", source.id, copy=False)
        with model._connection as connection:
            connection.execute(
                "CREATE TRIGGER reject_delete BEFORE DELETE ON category "
                "BEGIN SELECT RAISE(ABORT, 'blocked'); END"
            )

        with self.assertRaises(datamodel.DataModelError):
            model.delete_category(source.id)

        self.assertIs(buffer.value, pending)
        self.assertEqual(model.get_category(source.id).name, "Source")

    def test_failed_source_lookup_discards_transfer_after_category_deletion(self):
        model, buffer, service = self._create_service()
        source = model.add_category(datamodel.Category("Source"))
        unrelated = model.add_category(datamodel.Category("Unrelated"))
        service.stage("category", source.id, copy=False)
        error = datamodel.DataModelError("failed", "Source lookup failed")

        with (
            patch.object(model, "category_exist", side_effect=error),
            self.assertLogs("bttext.events", level="ERROR"),
        ):
            model.delete_category(unrelated.id)

        self.assertIsNone(buffer.value)
        self.assertEqual(model.get_category(source.id).name, "Source")
        self.assertIsNone(model.category_exist(unrelated.id))


if __name__ == "__main__":
    unittest.main()
