import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock


from core.datamodel import (
    Category,
    CategorySummary,
    CategoryValidationError,
    DataModel,
    DataModelError,
    EntityNotFoundError,
    Snippet,
    SnippetValidationError,
)
from core.events import EventEmitter


class RecordingEventEmitter:
    def __init__(self):
        self.events = []

    def emit(self, name, value):
        self.events.append((name, value))


class DataModelTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.database_file = (
            Path(self.temporary_directory.name) / "data.db"
        )
        self.events = RecordingEventEmitter()
        self.model = DataModel(self.events, self.database_file)
        self.addCleanup(self.model.close)

    def test_category_and_snippet_crud(self):
        category = self.model.add_category(Category("Initial category"))
        snippet = self.model.add_snippet(
            Snippet("Initial snippet", "Initial content", category.id, 2)
        )

        category.name = "Edited category"
        self.model.edit_category(category)
        snippet.name = "Edited snippet"
        snippet.content = "Edited content"
        snippet.weight = 3
        self.model.edit_snippet(snippet)

        self.assertEqual(
            self.model.get_category(category.id).name,
            "Edited category",
        )
        loaded_snippet = self.model.get_snippet(snippet.id)
        self.assertEqual(loaded_snippet.name, "Edited snippet")
        self.assertEqual(loaded_snippet.content, "Edited content")
        self.assertEqual(loaded_snippet.weight, 3)

        self.model.delete_snippet(snippet.id)
        with self.assertRaises(EntityNotFoundError):
            self.model.get_snippet(snippet.id)
        self.model.delete_category(category.id)
        with self.assertRaises(EntityNotFoundError):
            self.model.get_category(category.id)

    def test_event_listener_error_does_not_rollback_committed_change(self):
        events = EventEmitter()
        events.on(
            "category.added",
            Mock(side_effect=RuntimeError("listener failed")),
        )
        later_listener = Mock()
        events.on("category.added", later_listener)
        self.model.ee = events
        category = Category("Committed before event")

        with self.assertLogs("core.events", level="ERROR"):
            self.model.add_category(category)

        self.assertIsNotNone(category.id)
        later_listener.assert_called_once_with(category)
        self.assertEqual(
            self.model.get_category(category.id).name,
            "Committed before event",
        )

    def test_runtime_sqlite_read_error_is_translated(self):
        self.model._connection.close()

        with self.assertRaises(DataModelError) as raised:
            self.model.get_category(1)

        self.assertEqual(raised.exception.code, "database_operation_failed")
        self.assertIsInstance(raised.exception.__cause__, sqlite3.Error)

    def test_runtime_sqlite_generator_error_is_translated_during_iteration(self):
        categories = self.model.get_categories()
        self.model._connection.close()

        with self.assertRaises(DataModelError) as raised:
            list(categories)

        self.assertEqual(raised.exception.code, "database_operation_failed")
        self.assertIsInstance(raised.exception.__cause__, sqlite3.Error)

    def test_runtime_sqlite_write_error_is_translated(self):
        lock_connection = sqlite3.connect(
            self.database_file,
            autocommit=True,
        )
        self.addCleanup(lock_connection.close)
        lock_connection.execute("BEGIN IMMEDIATE")
        self.addCleanup(lock_connection.rollback)
        self.model._connection.execute("PRAGMA busy_timeout = 0")

        with self.assertRaises(DataModelError) as raised:
            self.model.add_category(Category("Blocked write"))

        self.assertEqual(raised.exception.code, "database_operation_failed")
        self.assertIsInstance(raised.exception.__cause__, sqlite3.OperationalError)

    def test_category_summaries_include_number_of_snippets(self):
        empty_category = self.model.add_category(Category("Empty"))
        filled_category = self.model.add_category(Category("Filled"))
        self.model.add_snippet(Snippet("First", "Content", filled_category.id))
        self.model.add_snippet(Snippet("Second", "Content", filled_category.id))

        summaries = {
            summary.category.name: summary
            for summary in self.model.get_category_summaries()
        }

        self.assertIsInstance(summaries[empty_category.name], CategorySummary)
        self.assertEqual(
            summaries[empty_category.name].number_of_snippets,
            0,
        )
        self.assertEqual(
            summaries[filled_category.name].number_of_snippets,
            2,
        )
        self.assertFalse(
            hasattr(
                next(iter(self.model.get_categories())),
                "number_of_snippets",
            )
        )

    def test_weight_is_preserved_by_all_read_methods(self):
        category = self.model.add_category(Category("Weights"))
        snippet = self.model.add_snippet(
            Snippet("Heavy", "Weighted content", category.id, 3)
        )

        self.assertEqual(self.model.get_snippet(snippet.id).weight, 3)
        self.assertEqual(
            list(self.model.get_snippets(category.id))[0].weight,
            3,
        )
        self.assertEqual(
            list(self.model.search_snippets("Weighted"))[0].weight,
            3,
        )

    def test_snippets_have_a_stable_weight_name_and_id_order(self):
        category = self.model.add_category(Category("Ordering"))
        snippets = [
            self.model.add_snippet(
                Snippet("Zulu", "Shared search term", category.id, 1)
            ),
            self.model.add_snippet(
                Snippet("beta", "Shared search term", category.id, 3)
            ),
            self.model.add_snippet(
                Snippet("Alpha", "Shared search term", category.id, 3)
            ),
        ]

        expected_ids = [snippets[2].id, snippets[1].id, snippets[0].id]
        self.assertEqual(
            [snippet.id for snippet in self.model.get_snippets(category.id)],
            expected_ids,
        )
        self.assertEqual(
            [snippet.id for snippet in self.model.search_snippets("Shared")],
            expected_ids,
        )

    def test_search_order_is_stable_for_equal_category_names(self):
        first_parent = self.model.add_category(Category("First parent"))
        second_parent = self.model.add_category(Category("Second parent"))
        first_category = self.model.add_category(
            Category("Shared", parent_id=first_parent.id)
        )
        second_category = self.model.add_category(
            Category("shared", parent_id=second_parent.id)
        )
        first_snippet = self.model.add_snippet(
            Snippet("Match", "First", first_category.id)
        )
        second_snippet = self.model.add_snippet(
            Snippet("Match", "Second", second_category.id)
        )

        self.assertEqual(
            [snippet.id for snippet in self.model.search_snippets("Match")],
            [first_snippet.id, second_snippet.id],
        )

    def test_duplicate_names_are_rejected(self):
        category = self.model.add_category(Category("Unique category"))
        with self.assertRaises(CategoryValidationError):
            self.model.add_category(Category("unique CATEGORY"))

        self.model.add_snippet(
            Snippet("Unique snippet", "First", category.id)
        )
        with self.assertRaises(SnippetValidationError):
            self.model.add_snippet(
                Snippet("unique SNIPPET", "Second", category.id)
            )

        other_category = self.model.add_category(Category("Other category"))
        self.model.add_snippet(
            Snippet("Unique snippet", "Allowed here", other_category.id)
        )

    def test_hotstring_is_persisted_and_exact_values_are_globally_unique(self):
        first_category = self.model.add_category(Category("First"))
        second_category = self.model.add_category(Category("Second"))
        snippet = self.model.add_snippet(
            Snippet(
                "Greeting",
                "Kind regards",
                first_category.id,
                hotstring="MfG",
            )
        )

        self.assertEqual(self.model.get_snippet(snippet.id).hotstring, "MfG")
        self.assertEqual(
            self.model.get_hotstring_snippets()[0].id,
            snippet.id,
        )
        differently_cased = self.model.add_snippet(
            Snippet(
                "Other",
                "Other content",
                second_category.id,
                hotstring="mfg",
            )
        )
        self.assertEqual(differently_cased.hotstring, "mfg")

        with self.assertRaises(SnippetValidationError) as context:
            self.model.add_snippet(
                Snippet(
                    "Duplicate",
                    "Duplicate content",
                    second_category.id,
                    hotstring="MfG",
                )
            )
        self.assertEqual(context.exception.code, "snippet_hotstring_duplicate")

    def test_hotstring_whitespace_is_rejected_and_empty_value_is_disabled(self):
        category = self.model.add_category(Category("Category"))
        with self.assertRaises(SnippetValidationError) as context:
            self.model.add_snippet(
                Snippet("Invalid", "Content", category.id, hotstring="m fg")
            )
        self.assertEqual(context.exception.code, "snippet_hotstring_whitespace")

        snippet = self.model.add_snippet(
            Snippet("Disabled", "Content", category.id, hotstring="   ")
        )
        self.assertIsNone(self.model.get_snippet(snippet.id).hotstring)

    def test_copy_does_not_duplicate_hotstring(self):
        source_category = self.model.add_category(Category("Source"))
        target_category = self.model.add_category(Category("Target"))
        source = self.model.add_snippet(
            Snippet(
                "Greeting",
                "Content",
                source_category.id,
                hotstring="greet",
            )
        )

        copied = self.model.copy_snippet(source.id, target_category.id)

        self.assertIsNone(copied.hotstring)
        self.assertEqual(self.model.get_snippet(source.id).hotstring, "greet")

    def test_category_unique_constraint_is_translated_to_domain_error(self):
        self.model.add_category(Category("Existing"))
        self.model.category_exist = Mock(return_value=None)

        with self.assertRaises(CategoryValidationError) as context:
            self.model.add_category(Category("EXISTING"))

        self.assertEqual(context.exception.code, "category_name_duplicate")
        self.assertIsInstance(context.exception.__cause__, sqlite3.IntegrityError)

    def test_category_foreign_key_constraint_is_translated_to_domain_error(self):
        self.model.category_exist = Mock(side_effect=(999, None))

        with self.assertRaises(CategoryValidationError) as context:
            self.model.add_category(Category("Child", parent_id=999))

        self.assertEqual(context.exception.code, "category_parent_missing")
        self.assertIsInstance(context.exception.__cause__, sqlite3.IntegrityError)

    def test_snippet_unique_constraint_is_translated_to_domain_error(self):
        category = self.model.add_category(Category("Category"))
        self.model.add_snippet(Snippet("Existing", "First", category.id))
        self.model.snippet_exist = Mock(return_value=None)

        with self.assertRaises(SnippetValidationError) as context:
            self.model.add_snippet(
                Snippet("EXISTING", "Second", category.id)
            )

        self.assertEqual(context.exception.code, "snippet_name_duplicate")
        self.assertIsInstance(context.exception.__cause__, sqlite3.IntegrityError)

    def test_snippet_foreign_key_constraint_is_translated_to_domain_error(self):
        self.model.category_exist = Mock(return_value=999)

        with self.assertRaises(SnippetValidationError) as context:
            self.model.add_snippet(Snippet("Orphan", "Content", 999))

        self.assertEqual(context.exception.code, "snippet_category_missing")
        self.assertIsInstance(context.exception.__cause__, sqlite3.IntegrityError)

    def test_snippet_check_constraint_is_translated_to_domain_error(self):
        category = self.model.add_category(Category("Category"))
        self.model.WEIGHTS = (1, 2, 3, 4)

        with self.assertRaises(SnippetValidationError) as context:
            self.model.add_snippet(
                Snippet("Invalid weight", "Content", category.id, 4)
            )

        self.assertEqual(context.exception.code, "snippet_weight_invalid")
        self.assertIsInstance(context.exception.__cause__, sqlite3.IntegrityError)

    def test_category_names_are_unique_only_among_siblings(self):
        first_parent = self.model.add_category(Category("First"))
        second_parent = self.model.add_category(Category("Second"))
        first_child = self.model.add_category(
            Category("Templates", parent_id=first_parent.id)
        )
        second_child = self.model.add_category(
            Category("Templates", parent_id=second_parent.id)
        )

        self.assertNotEqual(first_child.id, second_child.id)
        with self.assertRaises(CategoryValidationError):
            self.model.add_category(
                Category("TEMPLATES", parent_id=first_parent.id)
            )

    def test_category_path_and_direct_children(self):
        root = self.model.add_category(Category("Root"))
        child = self.model.add_category(
            Category("Child", parent_id=root.id)
        )
        grandchild = self.model.add_category(
            Category("Grandchild", parent_id=child.id)
        )

        self.assertEqual(
            self.model.get_category_path(grandchild.id),
            "Root / Child / Grandchild",
        )
        self.assertEqual(
            [category.id for category in self.model.get_category_children(root.id)],
            [child.id],
        )

    def test_category_cannot_be_moved_below_itself_or_a_descendant(self):
        root = self.model.add_category(Category("Root"))
        child = self.model.add_category(
            Category("Child", parent_id=root.id)
        )

        with self.assertRaises(CategoryValidationError):
            self.model.move_category(root.id, root.id)
        with self.assertRaises(CategoryValidationError):
            self.model.move_category(root.id, child.id)

        self.assertIsNone(self.model.get_category(root.id).parent_id)

    def test_category_subtree_can_be_moved_and_copied(self):
        source = self.model.add_category(Category("Source"))
        child = self.model.add_category(
            Category("Child", parent_id=source.id)
        )
        self.model.add_snippet(
            Snippet(
                "Nested",
                "Content",
                child.id,
                hotstring="nested",
            )
        )
        destination = self.model.add_category(Category("Destination"))

        self.model.move_category(source.id, destination.id)
        self.assertEqual(
            self.model.get_category(source.id).parent_id,
            destination.id,
        )

        copied = self.model.copy_category(source.id, None)
        copied_child = list(self.model.get_category_children(copied.id))[0]
        copied_snippet = list(self.model.get_snippets(copied_child.id))[0]
        self.assertEqual(copied.name, "Source")
        self.assertEqual(copied_child.name, "Child")
        self.assertEqual(copied_snippet.content, "Content")
        self.assertIsNone(copied_snippet.hotstring)

        with self.assertRaises(CategoryValidationError):
            self.model.copy_category(source.id, source.id)
        with self.assertRaises(CategoryValidationError):
            self.model.copy_category(source.id, child.id)

    def test_snippet_can_be_moved_and_copied_by_id(self):
        source = self.model.add_category(Category("Source"))
        destination = self.model.add_category(Category("Destination"))
        snippet = self.model.add_snippet(
            Snippet("Snippet", "Content", source.id, 3)
        )

        self.model.move_snippet(snippet.id, destination.id)
        self.assertEqual(
            self.model.get_snippet(snippet.id).category_id,
            destination.id,
        )
        copied = self.model.copy_snippet(snippet.id, source.id)
        self.assertEqual(copied.category_id, source.id)
        self.assertEqual(copied.weight, 3)

    def test_multiple_snippets_can_be_moved_and_copied_atomically(self):
        source = self.model.add_category(Category("Source"))
        destination = self.model.add_category(Category("Destination"))
        snippets = [
            self.model.add_snippet(Snippet("First", "One", source.id)),
            self.model.add_snippet(Snippet("Second", "Two", source.id, 3)),
        ]

        moved = self.model.move_snippets(
            [snippet.id for snippet in snippets],
            destination.id,
        )
        self.assertEqual(
            [snippet.category_id for snippet in moved],
            [destination.id] * 2,
        )

        copied = self.model.copy_snippets(
            [snippet.id for snippet in snippets],
            source.id,
        )
        self.assertEqual([snippet.name for snippet in copied], ["First", "Second"])
        self.assertEqual([snippet.weight for snippet in copied], [1, 3])

    def test_multiple_snippet_copy_rolls_back_on_name_conflict(self):
        source = self.model.add_category(Category("Source"))
        destination = self.model.add_category(Category("Destination"))
        first = self.model.add_snippet(Snippet("First", "One", source.id))
        second = self.model.add_snippet(Snippet("Second", "Two", source.id))
        self.model.add_snippet(Snippet("Second", "Existing", destination.id))

        with self.assertRaises(SnippetValidationError):
            self.model.copy_snippets([first.id, second.id], destination.id)

        self.assertEqual(
            [snippet.name for snippet in self.model.get_snippets(destination.id)],
            ["Second"],
        )

    def test_multiple_snippets_can_be_deleted_atomically(self):
        category = self.model.add_category(Category("Category"))
        snippets = [
            self.model.add_snippet(Snippet("First", "One", category.id)),
            self.model.add_snippet(Snippet("Second", "Two", category.id)),
        ]
        self.events.events.clear()

        deleted = self.model.delete_snippets(
            [snippet.id for snippet in snippets]
        )

        self.assertEqual(
            [snippet.id for snippet in deleted],
            [snippet.id for snippet in snippets],
        )
        self.assertEqual(list(self.model.get_snippets(category.id)), [])
        self.assertEqual(
            [
                snippet.id
                for event_name, snippet in self.events.events
                if event_name == "snippet.deleted"
            ],
            [snippet.id for snippet in snippets],
        )

    def test_multiple_snippet_delete_does_nothing_if_one_id_is_missing(self):
        category = self.model.add_category(Category("Category"))
        snippet = self.model.add_snippet(
            Snippet("Snippet", "Content", category.id)
        )

        with self.assertRaises(EntityNotFoundError):
            self.model.delete_snippets([snippet.id, 999999])

        self.assertEqual(self.model.get_snippet(snippet.id), snippet)

    def test_deleting_category_deletes_entire_subtree(self):
        root = self.model.add_category(Category("Root"))
        child = self.model.add_category(
            Category("Child", parent_id=root.id)
        )
        snippet = self.model.add_snippet(
            Snippet("Nested", "Content", child.id)
        )

        self.assertEqual(
            self.model.get_category_subtree_stats(root.id),
            (1, 1),
        )
        self.model.delete_category(root.id)

        with self.assertRaises(EntityNotFoundError):
            self.model.get_category(child.id)
        with self.assertRaises(EntityNotFoundError):
            self.model.get_snippet(snippet.id)

    def test_names_are_trimmed_and_whitespace_only_names_are_rejected(self):
        category = self.model.add_category(Category("  Trimmed category  "))
        snippet = self.model.add_snippet(
            Snippet("  Trimmed snippet  ", "Content", category.id)
        )

        self.assertEqual(category.name, "Trimmed category")
        self.assertEqual(snippet.name, "Trimmed snippet")
        self.assertEqual(
            self.model.get_category(category.id).name,
            "Trimmed category",
        )
        self.assertEqual(
            self.model.get_snippet(snippet.id).name,
            "Trimmed snippet",
        )

        with self.assertRaises(CategoryValidationError):
            self.model.add_category(Category("   "))
        with self.assertRaises(SnippetValidationError):
            self.model.add_snippet(Snippet("   ", "Content", category.id))

    def test_existing_names_can_change_case(self):
        category = self.model.add_category(Category("Category"))
        snippet = self.model.add_snippet(
            Snippet("Snippet", "Content", category.id)
        )

        category.name = "CATEGORY"
        snippet.name = "SNIPPET"

        self.model.edit_category(category)
        self.model.edit_snippet(snippet)

        self.assertEqual(self.model.get_category(category.id).name, "CATEGORY")
        self.assertEqual(self.model.get_snippet(snippet.id).name, "SNIPPET")

    def test_deleting_category_cascades_when_id_is_reused(self):
        category = self.model.add_category(Category("Old category"))
        old_id = category.id
        self.model.add_snippet(
            Snippet("Old snippet", "Must disappear", old_id)
        )

        self.model.delete_category(old_id)
        replacement = self.model.add_category(Category("Replacement"))

        self.assertEqual(replacement.id, old_id)
        self.assertEqual(list(self.model.get_snippets(replacement.id)), [])
        remaining = self.model._connection.execute(
            "SELECT COUNT(*) FROM snippet WHERE category_id = ?",
            (old_id,),
        ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_search_treats_like_metacharacters_as_literals(self):
        category = self.model.add_category(Category("Search"))
        snippets = {
            "%": self.model.add_snippet(
                Snippet("100% literal", "percent", category.id)
            ),
            "_": self.model.add_snippet(
                Snippet("under_score", "underscore", category.id)
            ),
            "\\": self.model.add_snippet(
                Snippet("backslash", "folder\\file", category.id)
            ),
        }
        self.model.add_snippet(
            Snippet("ordinary", "contains no metacharacter", category.id)
        )

        for term, expected in snippets.items():
            with self.subTest(term=term):
                results = list(self.model.search_snippets(term))
                self.assertEqual([result.id for result in results], [expected.id])


class DatabaseMigrationTestCase(unittest.TestCase):
    def test_empty_database_file_is_initialized(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "empty.db"
            database_file.touch()

            model = DataModel(RecordingEventEmitter(), database_file)
            try:
                tables = {
                    row[0]
                    for row in model._connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                self.assertEqual(tables, {"category", "snippet"})
                self.assertEqual(
                    model._connection.execute("PRAGMA user_version").fetchone()[0],
                    DataModel.SCHEMA_VERSION,
                )
            finally:
                model.close()

    def test_current_schema_enforces_additional_domain_checks(self):
        with ExitStack() as resources:
            temporary_directory = resources.enter_context(
                tempfile.TemporaryDirectory()
            )
            database_file = Path(temporary_directory) / "checks.db"
            model = DataModel(RecordingEventEmitter(), database_file)
            resources.callback(model.close)

            category = model.add_category(Category("Category"))
            invalid_statements = (
                (
                    "INSERT INTO category (name) VALUES (char(9) || ' ')",
                    (),
                ),
                (
                    "UPDATE category SET parent_id = id WHERE id = ?",
                    (category.id,),
                ),
                (
                    "INSERT INTO snippet "
                    "(category_id, name, content, weight) "
                    "VALUES (?, char(10) || ' ', 'Content', 1)",
                    (category.id,),
                ),
                (
                    "INSERT INTO snippet "
                    "(category_id, name, content, weight) "
                    "VALUES (?, 'Snippet', '', 1)",
                    (category.id,),
                ),
            )

            for sql, parameters in invalid_statements:
                with self.subTest(sql=sql):
                    with self.assertRaises(sqlite3.IntegrityError):
                        model._connection.execute(sql, parameters)
                    model._connection.rollback()

    def test_incomplete_database_schema_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "incomplete.db"
            connection = sqlite3.connect(database_file)
            connection.execute(
                "CREATE TABLE category (id INTEGER NOT NULL PRIMARY KEY, name TEXT)"
            )
            connection.close()

            with self.assertRaisesRegex(
                DataModelError,
                r"schema is incomplete.*snippet",
            ):
                DataModel(RecordingEventEmitter(), database_file)

    def test_corrupt_database_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "corrupt.db"
            database_file.write_bytes(b"This is not a SQLite database")

            with self.assertRaises(DataModelError) as context:
                DataModel(RecordingEventEmitter(), database_file)

            self.assertEqual(context.exception.code, "database_open_failed")
            self.assertIsInstance(
                context.exception.parameters["reason"],
                sqlite3.DatabaseError,
            )

    def test_database_with_foreign_key_violation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "invalid-foreign-key.db"
            model = DataModel(RecordingEventEmitter(), database_file)
            model.close()

            connection = sqlite3.connect(database_file)
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "INSERT INTO snippet "
                "(category_id, name, content, weight) "
                "VALUES (999, 'Orphan', 'Content', 1)"
            )
            connection.commit()
            connection.close()

            with self.assertRaises(DataModelError) as context:
                DataModel(RecordingEventEmitter(), database_file)

            self.assertEqual(
                context.exception.code,
                "database_foreign_key_violation",
            )

    def test_existing_mode_rejects_missing_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "missing.db"

            with self.assertRaises(DataModelError) as context:
                DataModel(
                    RecordingEventEmitter(),
                    database_file,
                    allow_create=False,
                )

            self.assertEqual(context.exception.code, "database_file_missing")
            self.assertFalse(database_file.exists())

    def test_existing_mode_rejects_empty_database(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "empty.db"
            database_file.touch()

            with self.assertRaises(DataModelError) as context:
                DataModel(
                    RecordingEventEmitter(),
                    database_file,
                    allow_create=False,
                )

            self.assertEqual(
                context.exception.code,
                "database_schema_incomplete",
            )

    def test_database_with_category_cycle_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "category-cycle.db"
            model = DataModel(RecordingEventEmitter(), database_file)
            model.close()

            connection = sqlite3.connect(database_file)
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "INSERT INTO category (id, parent_id, name) "
                "VALUES (1, 2, 'First')"
            )
            connection.execute(
                "INSERT INTO category (id, parent_id, name) "
                "VALUES (2, 1, 'Second')"
            )
            connection.commit()
            connection.close()

            with self.assertRaises(DataModelError) as context:
                DataModel(RecordingEventEmitter(), database_file)

            self.assertEqual(
                context.exception.code,
                "database_category_cycle",
            )

    def test_newer_database_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "newer.db"
            model = DataModel(RecordingEventEmitter(), database_file)
            model.close()

            newer_version = DataModel.SCHEMA_VERSION + 1
            connection = sqlite3.connect(database_file)
            connection.execute("PRAGMA user_version = {}".format(newer_version))
            connection.close()

            with self.assertRaisesRegex(
                DataModelError,
                r"newer version.*schema version: 6.*supported version: 5",
            ):
                DataModel(RecordingEventEmitter(), database_file)

    def test_legacy_database_is_migrated_with_data_and_constraints(self):
        with ExitStack() as resources:
            temporary_directory = resources.enter_context(
                tempfile.TemporaryDirectory()
            )
            database_file = Path(temporary_directory) / "legacy.db"
            connection = sqlite3.connect(database_file)
            connection.execute(
                "CREATE TABLE category (id INTEGER NOT NULL PRIMARY KEY, name TEXT UNIQUE)"
            )
            connection.execute(
                "CREATE TABLE snippet (id INTEGER NOT NULL PRIMARY KEY, category_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL, weight INTEGER DEFAULT 1, FOREIGN KEY (category_id) REFERENCES category (id) ON DELETE CASCADE)"
            )
            connection.execute(
                "INSERT INTO category (id, name) VALUES (7, 'Legacy')"
            )
            connection.execute(
                "INSERT INTO snippet (id, category_id, name, content, weight) VALUES (9, 7, 'Legacy snippet', 'Legacy content', 3)"
            )
            connection.commit()
            connection.close()

            model = DataModel(RecordingEventEmitter(), database_file)
            resources.callback(model.close)

            self.assertEqual(
                model._connection.execute("PRAGMA user_version").fetchone()[0],
                DataModel.SCHEMA_VERSION,
            )
            self.assertEqual(model.get_category(7).name, "Legacy")
            migrated_snippet = model.get_snippet(9)
            self.assertEqual(migrated_snippet.content, "Legacy content")
            self.assertEqual(migrated_snippet.weight, 3)

            with self.assertRaises(sqlite3.IntegrityError):
                model._connection.execute(
                    "INSERT INTO category (name) VALUES (NULL)"
                )
            model._connection.rollback()

            with self.assertRaises(sqlite3.IntegrityError):
                model._connection.execute(
                    "INSERT INTO snippet (category_id, name, content, weight) "
                    "VALUES (7, 'Invalid weight', 'content', 4)"
                )
            model._connection.rollback()

            with self.assertRaises(sqlite3.IntegrityError):
                model._connection.execute(
                    "INSERT INTO snippet (category_id, name, content, weight) "
                    "VALUES (7, 'Legacy snippet', 'duplicate', 1)"
                )
            model._connection.rollback()

    def test_migration_from_version_zero_adds_missing_weight_column(self):
        with ExitStack() as resources:
            temporary_directory = resources.enter_context(
                tempfile.TemporaryDirectory()
            )
            database_file = Path(temporary_directory) / "legacy-without-weight.db"
            connection = sqlite3.connect(database_file)
            connection.execute(
                "CREATE TABLE category "
                "(id INTEGER NOT NULL PRIMARY KEY, name TEXT UNIQUE)"
            )
            connection.execute(
                "CREATE TABLE snippet "
                "(id INTEGER NOT NULL PRIMARY KEY, category_id INTEGER NOT NULL, "
                "name TEXT NOT NULL, content TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO category (id, name) VALUES (1, 'Legacy')"
            )
            connection.execute(
                "INSERT INTO snippet (id, category_id, name, content) "
                "VALUES (2, 1, 'Without weight', 'Legacy content')"
            )
            connection.commit()
            connection.close()

            model = DataModel(RecordingEventEmitter(), database_file)
            resources.callback(model.close)

            self.assertEqual(model.get_snippet(2).weight, 1)
            self.assertEqual(
                model._connection.execute("PRAGMA user_version").fetchone()[0],
                DataModel.SCHEMA_VERSION,
            )

    def test_version_one_database_is_migrated_to_category_tree(self):
        with ExitStack() as resources:
            temporary_directory = resources.enter_context(
                tempfile.TemporaryDirectory()
            )
            database_file = Path(temporary_directory) / "version-one.db"
            connection = sqlite3.connect(database_file)
            connection.execute(
                "CREATE TABLE category "
                "(id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL UNIQUE)"
            )
            connection.execute(
                "CREATE TABLE snippet "
                "(id INTEGER NOT NULL PRIMARY KEY, category_id INTEGER NOT NULL, "
                "name TEXT NOT NULL, content TEXT NOT NULL, weight INTEGER NOT NULL "
                "DEFAULT 1 CHECK (weight IN (1, 2, 3)), "
                "UNIQUE (category_id, name), FOREIGN KEY (category_id) "
                "REFERENCES category (id) ON DELETE CASCADE)"
            )
            connection.execute(
                "INSERT INTO category (id, name) VALUES (7, 'Legacy')"
            )
            connection.execute(
                "INSERT INTO snippet "
                "(id, category_id, name, content, weight) "
                "VALUES (9, 7, 'Snippet', 'Content', 2)"
            )
            connection.execute("PRAGMA user_version = 1")
            connection.commit()
            connection.close()

            model = DataModel(RecordingEventEmitter(), database_file)
            resources.callback(model.close)

            category = model.get_category(7)
            self.assertIsNone(category.parent_id)
            self.assertEqual(model.get_snippet(9).category_id, 7)
            self.assertEqual(model._get_database_version(), 5)

    def test_version_four_hotstring_index_becomes_case_sensitive(self):
        with ExitStack() as resources:
            temporary_directory = resources.enter_context(
                tempfile.TemporaryDirectory()
            )
            database_file = Path(temporary_directory) / "version-four.db"
            model = DataModel(RecordingEventEmitter(), database_file)
            category = model.add_category(Category("Category"))
            model.add_snippet(
                Snippet(
                    "First",
                    "First content",
                    category.id,
                    hotstring="MfG",
                )
            )
            model._connection.execute("DROP INDEX snippet_hotstring_unique")
            model._connection.execute(
                "CREATE UNIQUE INDEX snippet_hotstring_unique "
                "ON snippet(hotstring COLLATE NOCASE) "
                "WHERE hotstring IS NOT NULL"
            )
            model._connection.execute("PRAGMA user_version = 4")
            model.close()

            migrated = DataModel(RecordingEventEmitter(), database_file)
            resources.callback(migrated.close)
            second = migrated.add_snippet(
                Snippet(
                    "Second",
                    "Second content",
                    category.id,
                    hotstring="mfg",
                )
            )

            self.assertEqual(migrated._get_database_version(), 5)
            self.assertEqual(second.hotstring, "mfg")
            with self.assertRaises(SnippetValidationError):
                migrated.add_snippet(
                    Snippet(
                        "Duplicate",
                        "Duplicate content",
                        category.id,
                        hotstring="MfG",
                    )
                )

    def test_version_two_database_gets_case_insensitive_snippet_constraint(self):
        with ExitStack() as resources:
            temporary_directory = resources.enter_context(
                tempfile.TemporaryDirectory()
            )
            database_file = Path(temporary_directory) / "version-two.db"
            connection = sqlite3.connect(database_file)
            connection.execute(
                "CREATE TABLE category ("
                "id INTEGER NOT NULL PRIMARY KEY, parent_id INTEGER, "
                "name TEXT NOT NULL, FOREIGN KEY (parent_id) "
                "REFERENCES category (id) ON DELETE CASCADE)"
            )
            connection.execute(
                "CREATE TABLE snippet ("
                "id INTEGER NOT NULL PRIMARY KEY, category_id INTEGER NOT NULL, "
                "name TEXT NOT NULL, content TEXT NOT NULL, "
                "weight INTEGER NOT NULL DEFAULT 1 CHECK (weight IN (1, 2, 3)), "
                "UNIQUE (category_id, name), FOREIGN KEY (category_id) "
                "REFERENCES category (id) ON DELETE CASCADE)"
            )
            connection.execute(
                "INSERT INTO category (id, name) VALUES (1, 'Category')"
            )
            connection.execute(
                "INSERT INTO snippet "
                "(id, category_id, name, content, weight) "
                "VALUES (2, 1, 'Snippet', 'Content', 1)"
            )
            connection.execute("PRAGMA user_version = 2")
            connection.commit()
            connection.close()

            model = DataModel(RecordingEventEmitter(), database_file)
            resources.callback(model.close)

            self.assertEqual(model._get_database_version(), 5)
            with self.assertRaises(sqlite3.IntegrityError):
                model._connection.execute(
                    "INSERT INTO snippet "
                    "(category_id, name, content, weight) "
                    "VALUES (1, 'SNIPPET', 'Other content', 1)"
                )
            model._connection.rollback()

    def test_version_two_migration_rejects_case_insensitive_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "duplicates.db"
            connection = sqlite3.connect(database_file)
            connection.execute(
                "CREATE TABLE category ("
                "id INTEGER NOT NULL PRIMARY KEY, parent_id INTEGER, "
                "name TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE snippet ("
                "id INTEGER NOT NULL PRIMARY KEY, category_id INTEGER NOT NULL, "
                "name TEXT NOT NULL, content TEXT NOT NULL, "
                "weight INTEGER NOT NULL DEFAULT 1, "
                "UNIQUE (category_id, name))"
            )
            connection.execute(
                "INSERT INTO category (id, name) VALUES (1, 'Category')"
            )
            connection.executemany(
                "INSERT INTO snippet "
                "(category_id, name, content, weight) VALUES (1, ?, ?, 1)",
                (("Snippet", "First"), ("SNIPPET", "Second")),
            )
            connection.execute("PRAGMA user_version = 2")
            connection.commit()
            connection.close()

            with self.assertRaises(DataModelError) as context:
                DataModel(RecordingEventEmitter(), database_file)

            self.assertEqual(
                context.exception.code,
                "database_snippet_names_duplicate_case_insensitive",
            )

            connection = sqlite3.connect(database_file)
            try:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0],
                    2,
                )
            finally:
                connection.close()

    def test_version_two_migration_rejects_new_check_constraint_violations(self):
        invalid_rows = (
            (
                "empty category name",
                "INSERT INTO category (id, parent_id, name) "
                "VALUES (2, NULL, '   ')",
                "database_category_name_empty",
            ),
            (
                "category is its own parent",
                "INSERT INTO category (id, parent_id, name) "
                "VALUES (2, 2, 'Self')",
                "database_category_own_parent",
            ),
            (
                "empty snippet name",
                "INSERT INTO snippet "
                "(category_id, name, content, weight) "
                "VALUES (1, '   ', 'Content', 1)",
                "database_snippet_name_empty",
            ),
            (
                "empty snippet content",
                "INSERT INTO snippet "
                "(category_id, name, content, weight) "
                "VALUES (1, 'Snippet', '', 1)",
                "database_snippet_content_empty",
            ),
        )

        for label, invalid_insert, expected_code in invalid_rows:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as directory:
                database_file = Path(directory) / "invalid-check.db"
                connection = sqlite3.connect(database_file)
                connection.execute(
                    "CREATE TABLE category ("
                    "id INTEGER NOT NULL PRIMARY KEY, parent_id INTEGER, "
                    "name TEXT NOT NULL, FOREIGN KEY (parent_id) "
                    "REFERENCES category (id) ON DELETE CASCADE)"
                )
                connection.execute(
                    "CREATE TABLE snippet ("
                    "id INTEGER NOT NULL PRIMARY KEY, "
                    "category_id INTEGER NOT NULL, name TEXT NOT NULL, "
                    "content TEXT NOT NULL, weight INTEGER NOT NULL DEFAULT 1 "
                    "CHECK (weight IN (1, 2, 3)), "
                    "UNIQUE (category_id, name), FOREIGN KEY (category_id) "
                    "REFERENCES category (id) ON DELETE CASCADE)"
                )
                connection.execute(
                    "INSERT INTO category (id, parent_id, name) "
                    "VALUES (1, NULL, 'Valid')"
                )
                connection.execute(invalid_insert)
                connection.execute("PRAGMA user_version = 2")
                connection.commit()
                connection.close()

                with self.assertRaises(DataModelError) as context:
                    DataModel(RecordingEventEmitter(), database_file)

                self.assertEqual(context.exception.code, expected_code)
                connection = sqlite3.connect(database_file)
                try:
                    self.assertEqual(
                        connection.execute(
                            "PRAGMA user_version"
                        ).fetchone()[0],
                        2,
                    )
                finally:
                    connection.close()


if __name__ == "__main__":
    unittest.main()
