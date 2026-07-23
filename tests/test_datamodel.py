import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path


try:
    import pymitter  # noqa: F401
except ModuleNotFoundError:
    class _PymitterEventEmitter:
        pass

    sys.modules["pymitter"] = types.SimpleNamespace(
        EventEmitter=_PymitterEventEmitter
    )

from datamodel import (
    Category,
    CategoryValidationError,
    DataModel,
    DataModelError,
    EntityNotFoundError,
    Snippet,
    SnippetValidationError,
)


class RecordingEventEmitter:
    def __init__(self):
        self.events = []

    def emit(self, name, value):
        self.events.append((name, value))


class RaisingEventEmitter:
    def emit(self, name, value):
        raise RuntimeError("listener failed")


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
        self.model.ee = RaisingEventEmitter()
        category = Category("Committed before event")

        with self.assertRaisesRegex(RuntimeError, "listener failed"):
            self.model.add_category(category)

        self.assertIsNotNone(category.id)
        self.assertEqual(
            self.model.get_category(category.id).name,
            "Committed before event",
        )

    def test_categories_include_number_of_snippets(self):
        empty_category = self.model.add_category(Category("Empty"))
        filled_category = self.model.add_category(Category("Filled"))
        self.model.add_snippet(Snippet("First", "Content", filled_category.id))
        self.model.add_snippet(Snippet("Second", "Content", filled_category.id))

        categories = {
            category.name: category
            for category in self.model.get_categories()
        }

        self.assertEqual(categories[empty_category.name].number_of_snippets, 0)
        self.assertEqual(categories[filled_category.name].number_of_snippets, 2)

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
        self.model.add_snippet(Snippet("Nested", "Content", child.id))
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

            with self.assertRaises(sqlite3.DatabaseError):
                DataModel(RecordingEventEmitter(), database_file)

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
                r"newer version.*schema version: 3.*supported version: 2",
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
                2,
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
            self.assertEqual(model._get_database_version(), 2)


if __name__ == "__main__":
    unittest.main()
