import sqlite3
import unittest
from unittest.mock import patch

from core.datamodel import DataModel
from core.model_errors import DataModelError
from core import migrations


class MigrationTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:", autocommit=True)
        self.addCleanup(self.connection.close)

    def test_registry_covers_every_supported_source_version(self):
        self.assertEqual(
            set(migrations.MIGRATIONS),
            set(range(migrations.SCHEMA_VERSION)),
        )
        self.assertEqual(DataModel.SCHEMA_VERSION, migrations.SCHEMA_VERSION)

    def test_missing_migration_is_rejected(self):
        with patch.dict(migrations.MIGRATIONS, {}, clear=True):
            with self.assertRaises(DataModelError) as raised:
                migrations.migrate_database(self.connection)

        self.assertEqual(raised.exception.code, "database_migration_unavailable")

    def test_migration_must_advance_exactly_one_version(self):
        def migration_without_version_change(connection):
            pass

        with patch.dict(
            migrations.MIGRATIONS,
            {0: migration_without_version_change},
            clear=True,
        ):
            with self.assertRaises(DataModelError) as raised:
                migrations.migrate_database(self.connection)

        self.assertEqual(raised.exception.code, "database_migration_failed")


if __name__ == "__main__":
    unittest.main()
