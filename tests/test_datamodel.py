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
            self.model.add_category(Category("Unique category"))

        self.model.add_snippet(
            Snippet("Unique snippet", "First", category.id)
        )
        with self.assertRaises(SnippetValidationError):
            self.model.add_snippet(
                Snippet("Unique snippet", "Second", category.id)
            )

        other_category = self.model.add_category(Category("Other category"))
        self.model.add_snippet(
            Snippet("Unique snippet", "Allowed here", other_category.id)
        )

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


if __name__ == "__main__":
    unittest.main()
