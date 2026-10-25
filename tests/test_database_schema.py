import sqlite3
import unittest

from core import database_schema
from core.datamodel import DataModel


class DatabaseSchemaTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:", autocommit=True)
        self.addCleanup(self.connection.close)

    def test_current_schema_contains_expected_tables_indexes_and_version(self):
        database_schema.create_current_schema(self.connection)

        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'index'"
            )
        }

        self.assertEqual(tables, {"category", "snippet"})
        self.assertTrue(
            {
                "category_root_name_unique",
                "category_child_name_unique",
                "snippet_category_name_unique",
                "snippet_hotstring_unique",
            }.issubset(indexes)
        )
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, database_schema.SCHEMA_VERSION)
        self.assertEqual(DataModel.SCHEMA_VERSION, database_schema.SCHEMA_VERSION)

        for table, expected_columns in database_schema.CURRENT_TABLE_COLUMNS.items():
            columns = {
                row[0]
                for row in self.connection.execute(
                    "SELECT name FROM pragma_table_info(?)", (table,)
                )
            }
            self.assertEqual(columns, expected_columns)
        self.assertEqual(
            database_schema.get_missing_current_columns(self.connection), ()
        )

    def test_missing_columns_are_reported_with_table_names_in_stable_order(self):
        self.connection.execute("CREATE TABLE category (id INTEGER PRIMARY KEY)")
        self.connection.execute("CREATE TABLE snippet (id INTEGER PRIMARY KEY)")

        self.assertEqual(
            database_schema.get_missing_current_columns(self.connection),
            (
                "category.name",
                "category.parent_id",
                "snippet.category_id",
                "snippet.content",
                "snippet.hotstring",
                "snippet.markdown_enabled",
                "snippet.name",
                "snippet.weight",
            ),
        )

    def test_column_validation_accepts_extra_and_case_insensitive_columns(self):
        self.connection.execute(
            "CREATE TABLE category (ID INTEGER, PARENT_ID INTEGER, NAME TEXT, extra TEXT)"
        )
        self.connection.execute(
            "CREATE TABLE snippet (ID INTEGER, CATEGORY_ID INTEGER, NAME TEXT, "
            "CONTENT TEXT, WEIGHT INTEGER, HOTSTRING TEXT, MARKDOWN_ENABLED INTEGER, "
            "extra TEXT)"
        )

        self.assertEqual(
            database_schema.get_missing_current_columns(self.connection), ()
        )


if __name__ == "__main__":
    unittest.main()
