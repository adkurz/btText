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


if __name__ == "__main__":
    unittest.main()
