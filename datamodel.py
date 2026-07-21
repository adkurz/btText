import sqlite3
import dataclasses 
from pathlib import Path

import pymitter


class DataModelError(Exception):
    """Base class for errors that can be shown to the user."""


class EntityNotFoundError(DataModelError):
    pass


class CategoryValidationError(DataModelError):
    pass


class SnippetValidationError(DataModelError):
    pass

@dataclasses.dataclass
class Snippet:
    name: str
    content: str
    category_id: int
    weight: int = 1
    id: int|None = None

@dataclasses.dataclass
class Category:
    name: str
    id: int|None = None
    number_of_snippets: int = 0


class DataModel:
    """
    Model to manage snippets and categories, stored in a SQLite3 Database

    Created by Adrian Kurz

    License: GNU GENERAL PUBLIC LICENSE, Version 3.0
    """

    WEIGHTS = (1, 2, 3)
    SCHEMA_VERSION = 1

    def __init__(self, ee: pymitter.EventEmitter, db_file: str | Path):
        self.ee = ee
        self._closed = False
        # Create database:
        db_file = Path(db_file)
        exists = db_file.exists()
        # Foreign-key enforcement must be enabled outside a transaction.
        self._connection = sqlite3.connect(db_file, autocommit=True)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        foreign_keys_enabled = self._connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]
        if not foreign_keys_enabled:
            self._connection.close()
            raise DataModelError("Could not enable SQLite foreign-key support")
        self._connection.autocommit = False
        if not exists:
            self.create_tables()
        else:
            self._updateDatabase()

    def create_tables(self):
        with self._connection as c:
            c.execute(
                "CREATE TABLE category (id INTEGER NOT NULL PRIMARY KEY, name TEXT NOT NULL UNIQUE)"
            )
            c.execute(
                "CREATE TABLE snippet (id INTEGER NOT NULL PRIMARY KEY, category_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL, weight INTEGER NOT NULL DEFAULT 1 CHECK (weight IN (1, 2, 3)), UNIQUE (category_id, name), FOREIGN KEY (category_id) REFERENCES category (id) ON DELETE CASCADE)"
            )
            c.execute("PRAGMA user_version = 1")

    def _updateDatabase(self):
        # Check for column weight in table snippet:
        if not self._has_table_column("snippet", "weight"):
            with self._connection as c:
                c.execute(
                    "ALTER TABLE snippet ADD COLUMN weight INTEGER DEFAULT 1"
                )
        if self._get_database_version() < self.SCHEMA_VERSION:
            self._migrate_to_schema_version_1()

    def _get_database_version(self) -> int:
        return self._connection.execute("PRAGMA user_version").fetchone()[0]

    def _migrate_to_schema_version_1(self) -> None:
        invalid_category_names = self._connection.execute(
            "SELECT COUNT(*) FROM category WHERE name IS NULL"
        ).fetchone()[0]
        if invalid_category_names:
            raise DataModelError(
                "The database contains categories without a name"
            )

        invalid_weights = self._connection.execute(
            "SELECT COUNT(*) FROM snippet "
            "WHERE weight IS NULL OR weight NOT IN (1, 2, 3)"
        ).fetchone()[0]
        if invalid_weights:
            raise DataModelError(
                "The database contains snippets with an invalid weight"
            )

        duplicate_snippet_names = self._connection.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT 1 FROM snippet GROUP BY category_id, name HAVING COUNT(*) > 1"
            ")"
        ).fetchone()[0]
        if duplicate_snippet_names:
            raise DataModelError(
                "The database contains duplicate snippet names in a category"
            )

        orphaned_snippets = self._connection.execute(
            "SELECT COUNT(*) FROM snippet s "
            "LEFT JOIN category c ON c.id = s.category_id WHERE c.id IS NULL"
        ).fetchone()[0]
        if orphaned_snippets:
            raise DataModelError(
                "The database contains snippets without a category"
            )

        with self._connection as c:
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

    def get_category(self, id: int) -> Category:
        result = self._connection.execute(
            "SELECT id, name  FROM category WHERE id = :id",
            {"id": id},
        )
        category = result.fetchone()
        if category is None:
            raise EntityNotFoundError(
                "Category with ID {} does not exist".format(id)
            )
        return Category(id=category['id'], name=category['name'])

    def get_categories(self, order: bool = False):
        sql = "SELECT id, name, (SELECT COUNT(*) FROM snippet WHERE category_id = category.id) AS number_of_snippets FROM category"
        if order:
            sql += " ORDER BY name COLLATE NOCASE"
        for category in self._connection.execute(sql):
            yield Category(
                id=category['id'],
                name=category['name'],
                number_of_snippets=category['number_of_snippets'],
            )

    def get_snippets(self, category_id: int, order_by_name: bool = False):
        sql = "SELECT id, category_id, name, weight, content FROM snippet WHERE category_id = ? ORDER BY weight DESC"
        if order_by_name:
            sql += ", name COLLATE NOCASE"
        for snippet in self._connection.execute(sql, (category_id,)):
            yield Snippet(
                id=snippet["id"],
                category_id=snippet["category_id"],
                name=snippet["name"],
                content=snippet["content"],
                weight=snippet["weight"],
            )

    def search_snippets(self, term: str):
        if not term:
            return None  # Find nothing for no therm!
        sql = "SELECT s.id, s.category_id, c.name AS category_name, s.name, s.weight, s.content FROM snippet s INNER JOIN category c ON s.category_id = c.id WHERE s.name LIKE :term ESCAPE '\\' OR s.content LIKE :term ESCAPE '\\' ORDER BY category_name, s.weight DESC, s.name COLLATE NOCASE"
        for snippet in self._connection.execute(
            sql, {"term": "%" + self._escape_like(term) + "%"}
        ):
            yield Snippet(
                id=snippet["id"],
                category_id=snippet["category_id"],
                name=snippet["name"],
                content=snippet["content"],
                weight=snippet["weight"],
            )

    def get_snippet(self, id: int) -> Snippet:
        result = self._connection.execute(
            "SELECT id, category_id, name, weight, content FROM snippet WHERE id = ?",
            (id,),
        )
        snippet = result.fetchone()
        if snippet is None:
            raise EntityNotFoundError(
                "Snippet with ID {} does not exist".format(id)
            )
        return Snippet(
            id=snippet["id"],
            category_id=snippet["category_id"],
            name=snippet["name"],
            content=snippet["content"],
            weight=snippet["weight"],
        )

    def category_exist(self, name_or_id: str | int) -> int | None:
        if isinstance(name_or_id, str):
            result = self._connection.execute(
                "SELECT id FROM category WHERE name = ?", (name_or_id,)
            )
        else:
            result = self._connection.execute(
                "SELECT id FROM category WHERE id = ?", (name_or_id,)
            )
        result = result.fetchone()
        return result["id"] if result is not None else None

    def snippet_exist(
        self, name_or_id: str | int, category_id: int | None = None
    ) -> int | None:
        if category_id is not None:
            result = self._connection.execute(
                "SELECT id FROM snippet WHERE name = ? AND category_id = ?",
                (
                    name_or_id,
                    category_id,
                ),
            )
        else:
            result = self._connection.execute(
                "SELECT id FROM snippet WHERE id = ?", (name_or_id,)
            )
        result = result.fetchone()
        return result["id"] if result is not None else None

    def add_category(self, category: Category) -> Category:
        # Check that name doesn't exist
        if self.category_exist(category.name):
            raise CategoryValidationError(
                "A category with this name already exists"
            )
        with self._connection as c:
            result = c.execute(
                "INSERT INTO category (name) VALUES (?)", (category.name,)
            )
            category.id = result.lastrowid
            self.ee.emit("category.added", category)
            return category

    def edit_category(self, category: Category) -> Category:
        # Check that category exists:
        if category.id is None:
            raise CategoryValidationError("The category has no ID")
        old_category = self.get_category(category.id)
        # Check that new name doesn't exist:
        if old_category.name != category.name and self.category_exist(
            category.name
        ):
            raise CategoryValidationError(
                "A category with this name already exists"
            )
        with self._connection as c:
            c.execute(
                "UPDATE category SET name = ? WHERE id = ?",
                (
                    category.name,
                    category.id
                ),
            )
            self.ee.emit("category.edited", category)
            return category

    def delete_category(self, id: int) -> Category:
        category = self.get_category(id)
        with self._connection as c:
            # Keep the operation safe even for databases created while foreign
            # key enforcement was disabled.
            c.execute("DELETE FROM snippet WHERE category_id = ?", (id,))
            c.execute("DELETE FROM category WHERE id = ?", (id,))
        self.ee.emit("category.deleted", id)
        return category

    def validate_snippet(self, snippet: Snippet) -> None:
        # Check  that the name isn't empty:
        if snippet.name == "":
            raise SnippetValidationError("The name must not be empty")
        # Check  that the content isn't empty:
        if snippet.content == "":
            raise SnippetValidationError(
                "The content must not be empty",
            )
        # Check that category id exists:
        if not self.category_exist(snippet.category_id):
            raise SnippetValidationError(
                "This category doesn't exist",
            )
        # Check that name in the same category doesn't exist:
        old_id = self.snippet_exist(snippet.name, snippet.category_id)
        id = snippet.id
        if old_id is not None and id != old_id:
            raise SnippetValidationError(
                "There is already a snippet with this name in this category"
            )
        # Check that weight is in the allowed range:
        if snippet.weight not in self.WEIGHTS:
            raise SnippetValidationError("The weight isn't in the allowed range.")

    def add_snippet(self, snippet: Snippet) -> Snippet:
        self.validate_snippet(snippet)
        with self._connection as c:
            result = c.execute(
                "INSERT INTO snippet (name, category_id, weight, content) VALUES (?, ?, ?, ?)",
                (
                    snippet.name,
                    snippet.category_id,
                    snippet.weight,
                    snippet.content
                )
            )
        snippet.id = result.lastrowid
        self.ee.emit("snippet.added", snippet)
        return snippet

    def edit_snippet(self, snippet: Snippet) -> Snippet:
        # Check that snippet id exists:
        if snippet.id is None:
            raise SnippetValidationError("The snippet has no ID")
        self.get_snippet(snippet.id)
        self.validate_snippet(snippet)
        with self._connection as c:
            c.execute(
                "UPDATE snippet SET name = ?, category_id = ?, weight = ?, content = ? WHERE id = ?",
                (
                    snippet.name,
                    snippet.category_id,
                    snippet.weight,
                    snippet.content,
                    snippet.id
                )
            )
            self.ee.emit("snippet.edited", snippet)
        return snippet

    def delete_snippet(self, id: int) -> dict:
        snippet = self.get_snippet(id)
        with self._connection as c:
            c.execute("DELETE FROM snippet WHERE id = ?", (id,))
            self.ee.emit("snippet.deleted", snippet)
            return snippet

    def _has_table_column(self, table: str, column: str) -> bool:
        result = self._connection.execute(
            "SELECT COUNT(*) AS CNTREC FROM pragma_table_info(?) WHERE name=?",
            (table, column),
        )
        return result.fetchone()["CNTREC"] > 0

    def _escape_like(self, string: str) -> str:
        return string.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True
