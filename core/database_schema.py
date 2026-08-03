"""Definition of the current btText SQLite database schema."""

import sqlite3


SCHEMA_VERSION = 5


def create_category_indexes(connection: sqlite3.Connection) -> None:
    """Create indexes that enforce unique category names per tree level."""
    # Separate partial indexes make names case-insensitively unique among
    # siblings while still permitting the same name in different branches.
    connection.execute(
        "CREATE UNIQUE INDEX category_root_name_unique "
        "ON category(name COLLATE NOCASE) WHERE parent_id IS NULL"
    )
    connection.execute(
        "CREATE UNIQUE INDEX category_child_name_unique "
        "ON category(parent_id, name COLLATE NOCASE) "
        "WHERE parent_id IS NOT NULL"
    )


def create_snippet_indexes(connection: sqlite3.Connection) -> None:
    """Create indexes that enforce case-insensitive snippet uniqueness."""
    connection.execute(
        "CREATE UNIQUE INDEX snippet_category_name_unique "
        "ON snippet(category_id, name COLLATE NOCASE)"
    )


def create_current_schema(connection: sqlite3.Connection) -> None:
    """Create the current schema in a new or empty database."""
    with connection as c:
        c.execute(
            "CREATE TABLE category ("
            "id INTEGER NOT NULL PRIMARY KEY, parent_id INTEGER, "
            "name TEXT NOT NULL CHECK (length(trim(name, "
            "char(9) || char(10) || char(11) || char(12) || "
            "char(13) || ' ')) > 0), "
            "CHECK (parent_id IS NULL OR parent_id <> id), "
            "FOREIGN KEY (parent_id) REFERENCES category (id) "
            "ON DELETE CASCADE)"
        )
        c.execute(
            "CREATE TABLE snippet ("
            "id INTEGER NOT NULL PRIMARY KEY, category_id INTEGER NOT NULL, "
            "name TEXT NOT NULL CHECK (length(trim(name, "
            "char(9) || char(10) || char(11) || char(12) || "
            "char(13) || ' ')) > 0), "
            "content TEXT NOT NULL CHECK (length(content) > 0), "
            "hotstring TEXT CHECK (hotstring IS NULL OR length(hotstring) > 0), "
            "weight INTEGER NOT NULL DEFAULT 1 "
            "CHECK (weight IN (1, 2, 3)), "
            "UNIQUE (category_id, name), "
            "FOREIGN KEY (category_id) REFERENCES category (id) "
            "ON DELETE CASCADE)"
        )
        create_category_indexes(c)
        create_snippet_indexes(c)
        c.execute(
            "CREATE UNIQUE INDEX snippet_hotstring_unique "
            "ON snippet(hotstring) "
            "WHERE hotstring IS NOT NULL"
        )
        c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
