"""Sequential SQLite schema migrations for btText databases."""

import sqlite3
from collections.abc import Callable

from core.database_schema import (
    SCHEMA_VERSION,
    create_category_indexes,
    create_snippet_indexes,
)
from core.model_errors import DataModelError


Migration = Callable[[sqlite3.Connection], None]


def _has_table_column(
    connection: sqlite3.Connection, table: str, column: str
) -> bool:
    """Return whether a SQLite table contains a named column."""
    result = connection.execute(
        "SELECT COUNT(*) AS CNTREC FROM pragma_table_info(?) WHERE name=?",
        (table, column),
    )
    return result.fetchone()[0] > 0


def migrate_from_0_to_1(connection: sqlite3.Connection) -> None:
    """Add snippet weights and rebuild legacy tables with constraints."""
    if not _has_table_column(connection, "snippet", "weight"):
        connection.execute(
            "ALTER TABLE snippet ADD COLUMN weight INTEGER DEFAULT 1"
        )

    invalid_category_names = connection.execute(
        "SELECT COUNT(*) FROM category WHERE name IS NULL"
    ).fetchone()[0]
    if invalid_category_names:
        raise DataModelError(
            "database_category_name_missing",
            "The database contains categories without a name",
        )

    invalid_weights = connection.execute(
        "SELECT COUNT(*) FROM snippet "
        "WHERE weight IS NULL OR weight NOT IN (1, 2, 3)"
    ).fetchone()[0]
    if invalid_weights:
        raise DataModelError(
            "database_snippet_weight_invalid",
            "The database contains snippets with an invalid weight",
        )

    duplicate_snippet_names = connection.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT 1 FROM snippet GROUP BY category_id, name HAVING COUNT(*) > 1"
        ")"
    ).fetchone()[0]
    if duplicate_snippet_names:
        raise DataModelError(
            "database_snippet_names_duplicate",
            "The database contains duplicate snippet names in a category",
        )

    orphaned_snippets = connection.execute(
        "SELECT COUNT(*) FROM snippet s "
        "LEFT JOIN category c ON c.id = s.category_id WHERE c.id IS NULL"
    ).fetchone()[0]
    if orphaned_snippets:
        raise DataModelError(
            "database_snippet_category_missing",
            "The database contains snippets without a category",
        )

    with connection as c:
        c.execute(
            "CREATE TABLE category_new (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL UNIQUE)"
        )
        c.execute(
            "CREATE TABLE snippet_new (id INTEGER NOT NULL PRIMARY KEY, category_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL, weight INTEGER NOT NULL DEFAULT 1 CHECK (weight IN (1, 2, 3)), UNIQUE (category_id, name), FOREIGN KEY (category_id) REFERENCES category_new (id) ON DELETE CASCADE)"
        )
        c.execute(
            "INSERT INTO category_new (id, name) SELECT id, name FROM category"
        )
        c.execute(
            "INSERT INTO snippet_new (id, category_id, name, content, weight) "
            "SELECT id, category_id, name, content, weight FROM snippet"
        )
        c.execute("DROP TABLE snippet")
        c.execute("DROP TABLE category")
        c.execute("ALTER TABLE category_new RENAME TO category")
        c.execute("ALTER TABLE snippet_new RENAME TO snippet")
        c.execute("PRAGMA user_version = 1")


def migrate_from_1_to_2(connection: sqlite3.Connection) -> None:
    """Replace the flat category table with a hierarchical schema."""
    with connection as c:
        c.execute(
            "CREATE TABLE category_new (id INTEGER NOT NULL PRIMARY KEY, "
            "parent_id INTEGER, name TEXT NOT NULL, "
            "FOREIGN KEY (parent_id) REFERENCES category_new (id) ON DELETE CASCADE)"
        )
        c.execute(
            "INSERT INTO category_new (id, parent_id, name) "
            "SELECT id, NULL, name FROM category"
        )
        c.execute(
            "CREATE TABLE snippet_new (id INTEGER NOT NULL PRIMARY KEY, "
            "category_id INTEGER NOT NULL, name TEXT NOT NULL, "
            "content TEXT NOT NULL, weight INTEGER NOT NULL DEFAULT 1 "
            "CHECK (weight IN (1, 2, 3)), UNIQUE (category_id, name), "
            "FOREIGN KEY (category_id) REFERENCES category_new (id) "
            "ON DELETE CASCADE)"
        )
        c.execute(
            "INSERT INTO snippet_new (id, category_id, name, content, weight) "
            "SELECT id, category_id, name, content, weight FROM snippet"
        )
        c.execute("DROP TABLE snippet")
        c.execute("DROP TABLE category")
        c.execute("ALTER TABLE category_new RENAME TO category")
        c.execute("ALTER TABLE snippet_new RENAME TO snippet")
        create_category_indexes(c)
        c.execute("PRAGMA user_version = 2")


def migrate_from_2_to_3(connection: sqlite3.Connection) -> None:
    """Add case-insensitive uniqueness and domain checks to the schema."""
    invalid_category_names = connection.execute(
        "SELECT COUNT(*) FROM category "
        "WHERE length(trim(name, char(9) || char(10) || char(11) || "
        "char(12) || char(13) || ' ')) = 0"
    ).fetchone()[0]
    if invalid_category_names:
        raise DataModelError(
            "database_category_name_empty",
            "The database contains categories with an empty name",
        )

    invalid_category_parents = connection.execute(
        "SELECT COUNT(*) FROM category WHERE parent_id = id"
    ).fetchone()[0]
    if invalid_category_parents:
        raise DataModelError(
            "database_category_own_parent",
            "The database contains a category that is its own parent",
        )

    invalid_snippet_names = connection.execute(
        "SELECT COUNT(*) FROM snippet "
        "WHERE length(trim(name, char(9) || char(10) || char(11) || "
        "char(12) || char(13) || ' ')) = 0"
    ).fetchone()[0]
    if invalid_snippet_names:
        raise DataModelError(
            "database_snippet_name_empty",
            "The database contains snippets with an empty name",
        )

    invalid_snippet_contents = connection.execute(
        "SELECT COUNT(*) FROM snippet WHERE length(content) = 0"
    ).fetchone()[0]
    if invalid_snippet_contents:
        raise DataModelError(
            "database_snippet_content_empty",
            "The database contains snippets with empty content",
        )

    duplicate_snippet_names = connection.execute(
        "SELECT COUNT(*) FROM ("
        "SELECT 1 FROM snippet "
        "GROUP BY category_id, name COLLATE NOCASE HAVING COUNT(*) > 1"
        ")"
    ).fetchone()[0]
    if duplicate_snippet_names:
        raise DataModelError(
            "database_snippet_names_duplicate_case_insensitive",
            "The database contains snippet names that differ only in "
            "letter case within the same category",
        )

    with connection as c:
        c.execute(
            "CREATE TABLE category_new ("
            "id INTEGER NOT NULL PRIMARY KEY, parent_id INTEGER, "
            "name TEXT NOT NULL CHECK (length(trim(name, "
            "char(9) || char(10) || char(11) || char(12) || "
            "char(13) || ' ')) > 0), "
            "CHECK (parent_id IS NULL OR parent_id <> id), "
            "FOREIGN KEY (parent_id) REFERENCES category_new (id) "
            "ON DELETE CASCADE)"
        )
        c.execute(
            "INSERT INTO category_new (id, parent_id, name) "
            "SELECT id, parent_id, name FROM category"
        )
        c.execute(
            "CREATE TABLE snippet_new ("
            "id INTEGER NOT NULL PRIMARY KEY, category_id INTEGER NOT NULL, "
            "name TEXT NOT NULL CHECK (length(trim(name, "
            "char(9) || char(10) || char(11) || char(12) || "
            "char(13) || ' ')) > 0), "
            "content TEXT NOT NULL CHECK (length(content) > 0), "
            "weight INTEGER NOT NULL DEFAULT 1 "
            "CHECK (weight IN (1, 2, 3)), "
            "UNIQUE (category_id, name), "
            "FOREIGN KEY (category_id) REFERENCES category_new (id) "
            "ON DELETE CASCADE)"
        )
        c.execute(
            "INSERT INTO snippet_new "
            "(id, category_id, name, content, weight) "
            "SELECT id, category_id, name, content, weight FROM snippet"
        )
        c.execute("DROP TABLE snippet")
        c.execute("DROP TABLE category")
        c.execute("ALTER TABLE category_new RENAME TO category")
        c.execute("ALTER TABLE snippet_new RENAME TO snippet")
        create_category_indexes(c)
        create_snippet_indexes(c)
        c.execute("PRAGMA user_version = 3")


def migrate_from_3_to_4(connection: sqlite3.Connection) -> None:
    """Add optional globally unique hotstrings to snippets."""
    with connection as c:
        c.execute("ALTER TABLE snippet ADD COLUMN hotstring TEXT")
        c.execute(
            "CREATE UNIQUE INDEX snippet_hotstring_unique "
            "ON snippet(hotstring COLLATE NOCASE) "
            "WHERE hotstring IS NOT NULL"
        )
        c.execute("PRAGMA user_version = 4")


def migrate_from_4_to_5(connection: sqlite3.Connection) -> None:
    """Make hotstring uniqueness case-sensitive."""
    with connection as c:
        c.execute("DROP INDEX snippet_hotstring_unique")
        c.execute(
            "CREATE UNIQUE INDEX snippet_hotstring_unique "
            "ON snippet(hotstring) WHERE hotstring IS NOT NULL"
        )
        c.execute("PRAGMA user_version = 5")


MIGRATIONS: dict[int, Migration] = {
    0: migrate_from_0_to_1,
    1: migrate_from_1_to_2,
    2: migrate_from_2_to_3,
    3: migrate_from_3_to_4,
    4: migrate_from_4_to_5,
}


def get_database_version(connection: sqlite3.Connection) -> int:
    """Return SQLite's application-defined schema version."""
    return connection.execute("PRAGMA user_version").fetchone()[0]


def migrate_database(connection: sqlite3.Connection) -> None:
    """Apply each schema migration exactly once and in version order."""
    database_version = get_database_version(connection)
    if database_version > SCHEMA_VERSION:
        raise DataModelError(
            "database_version_too_new",
            "The database was created by a newer version of the application "
            "and cannot be opened (database schema version: "
            "{database_version}; supported version: {supported_version}).",
            database_version=database_version,
            supported_version=SCHEMA_VERSION,
        )

    while database_version < SCHEMA_VERSION:
        try:
            migration = MIGRATIONS[database_version]
        except KeyError as error:
            raise DataModelError(
                "database_migration_unavailable",
                "No database migration is available from schema version "
                "{database_version}.",
                database_version=database_version,
            ) from error

        migration(connection)
        migrated_version = get_database_version(connection)
        if migrated_version != database_version + 1:
            raise DataModelError(
                "database_migration_failed",
                "Database migration {migration_name} did not advance the "
                "schema from version {old_version} to version {new_version}.",
                migration_name=migration.__name__,
                old_version=database_version,
                new_version=database_version + 1,
            )
        database_version = migrated_version
