"""Persistence and domain operations for categories and text snippets."""

import sqlite3
import dataclasses 
from pathlib import Path

import pymitter


class DataModelError(Exception):
    """Base class for errors that can be shown to the user."""


class EntityNotFoundError(DataModelError):
    """Raised when an operation refers to an entity that no longer exists."""


class CategoryValidationError(DataModelError):
    """Raised when a category violates naming or tree constraints."""


class SnippetValidationError(DataModelError):
    """Raised when a snippet violates naming, weight, or category constraints."""

@dataclasses.dataclass
class Snippet:
    """A reusable text fragment assigned to one category.

    ``id`` is absent until the snippet is persisted. Higher ``weight`` values
    sort before lower values.
    """
    name: str
    content: str
    category_id: int
    weight: int = 1
    id: int|None = None

@dataclasses.dataclass
class Category:
    """A node in the category tree.

    ``number_of_snippets`` is a query-derived display value rather than a
    persisted property.
    """
    name: str
    id: int|None = None
    number_of_snippets: int = 0
    parent_id: int|None = None


class DataModel:
    """Manage the category tree and snippets stored in a SQLite database.

    Mutations commit before publishing model events, allowing listeners to
    reload entities without observing a partially applied transaction.
    """

    WEIGHTS = (1, 2, 3)
    SCHEMA_VERSION = 2
    MIGRATIONS = ("_migrate_from_0_to_1", "_migrate_from_1_to_2")

    def __init__(self, ee: pymitter.EventEmitter, db_file: str | Path):
        """Open, validate, and if necessary migrate the SQLite database."""
        self.ee = ee
        self._closed = False
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
        try:
            tables = self._get_table_names()
            if not exists or not tables:
                self.create_tables()
            else:
                missing_tables = {"category", "snippet"} - tables
                if missing_tables:
                    raise DataModelError(
                        "The database schema is incomplete. Missing table(s): {}".format(
                            ", ".join(sorted(missing_tables))
                        )
                    )
                self._migrate_database()
        except Exception:
            self._connection.close()
            self._closed = True
            raise

    def create_tables(self):
        """Create the current schema in a new or empty database."""
        with self._connection as c:
            c.execute(
                "CREATE TABLE category (id INTEGER NOT NULL PRIMARY KEY, parent_id INTEGER, name TEXT NOT NULL, FOREIGN KEY (parent_id) REFERENCES category (id) ON DELETE CASCADE)"
            )
            c.execute(
                "CREATE TABLE snippet (id INTEGER NOT NULL PRIMARY KEY, category_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL, weight INTEGER NOT NULL DEFAULT 1 CHECK (weight IN (1, 2, 3)), UNIQUE (category_id, name), FOREIGN KEY (category_id) REFERENCES category (id) ON DELETE CASCADE)"
            )
            self._create_category_indexes(c)
            c.execute("PRAGMA user_version = 2")

    def _migrate_database(self) -> None:
        """Apply each schema migration exactly once and in version order."""
        database_version = self._get_database_version()
        if database_version > self.SCHEMA_VERSION:
            raise DataModelError(
                "The database was created by a newer version of the application "
                "and cannot be opened (database schema version: {}; supported "
                "version: {}).".format(database_version, self.SCHEMA_VERSION)
            )

        while database_version < self.SCHEMA_VERSION:
            try:
                migration_name = self.MIGRATIONS[database_version]
            except IndexError as error:
                raise DataModelError(
                    "No database migration is available from schema version {}.".format(
                        database_version
                    )
                ) from error

            migration = getattr(self, migration_name)
            migration()
            migrated_version = self._get_database_version()
            if migrated_version != database_version + 1:
                raise DataModelError(
                    "Database migration {} did not advance the schema from "
                    "version {} to version {}.".format(
                        migration_name,
                        database_version,
                        database_version + 1,
                    )
                )
            database_version = migrated_version

    def _get_database_version(self) -> int:
        """Return SQLite's application-defined schema version."""
        return self._connection.execute("PRAGMA user_version").fetchone()[0]

    def _migrate_from_0_to_1(self) -> None:
        """Add snippet weights and rebuild legacy tables with constraints."""
        # Validate legacy data before rebuilding tables with stricter
        # constraints; otherwise SQLite would report an opaque copy failure.
        if not self._has_table_column("snippet", "weight"):
            self._connection.execute(
                "ALTER TABLE snippet ADD COLUMN weight INTEGER DEFAULT 1"
            )

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

    def _migrate_from_1_to_2(self) -> None:
        """Replace the flat category table with a hierarchical schema."""
        # SQLite cannot add the self-referencing foreign key in place, so both
        # related tables are rebuilt within one transaction.
        with self._connection as c:
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
            self._create_category_indexes(c)
            c.execute("PRAGMA user_version = 2")

    @staticmethod
    def _create_category_indexes(connection) -> None:
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

    def get_category(self, id: int) -> Category:
        """Return one category or raise :class:`EntityNotFoundError`."""
        result = self._connection.execute(
            "SELECT id, parent_id, name FROM category WHERE id = :id",
            {"id": id},
        )
        category = result.fetchone()
        if category is None:
            raise EntityNotFoundError(
                "Category with ID {} does not exist".format(id)
            )
        return Category(
            id=category["id"],
            parent_id=category["parent_id"],
            name=category["name"],
        )

    def get_categories(
        self,
        order: bool = False,
        parent_id: int | None = None,
        all_categories: bool = True,
    ):
        """Yield categories, optionally ordered or limited to direct children."""
        sql = (
            "SELECT id, parent_id, name, "
            "(SELECT COUNT(*) FROM snippet "
            "WHERE category_id = category.id) AS number_of_snippets "
            "FROM category"
        )
        parameters = ()
        if not all_categories:
            if parent_id is None:
                sql += " WHERE parent_id IS NULL"
            else:
                sql += " WHERE parent_id = ?"
                parameters = (parent_id,)
        if order:
            sql += " ORDER BY name COLLATE NOCASE"
        for category in self._connection.execute(sql, parameters):
            yield Category(
                id=category['id'],
                parent_id=category["parent_id"],
                name=category['name'],
                number_of_snippets=category['number_of_snippets'],
            )

    def get_category_children(self, parent_id: int | None):
        """Yield direct children of a category, ordered by name."""
        return self.get_categories(
            order=True,
            parent_id=parent_id,
            all_categories=False,
        )

    def get_category_path(self, id: int) -> str:
        """Return a display path ordered from the root to the category."""
        self.get_category(id)
        row = self._connection.execute(
            "WITH RECURSIVE ancestors(id, parent_id, name, depth) AS ("
            "SELECT id, parent_id, name, 0 FROM category WHERE id = ? "
            "UNION ALL "
            "SELECT c.id, c.parent_id, c.name, ancestors.depth + 1 "
            "FROM category c JOIN ancestors ON c.id = ancestors.parent_id"
            ") SELECT GROUP_CONCAT(name, ' / ') AS path FROM ("
            "SELECT name FROM ancestors ORDER BY depth DESC)",
            (id,),
        ).fetchone()
        return row["path"]

    def get_category_subtree_stats(self, id: int) -> tuple[int, int]:
        """Return descendant-category and snippet counts for a subtree."""
        self.get_category(id)
        row = self._connection.execute(
            "WITH RECURSIVE subtree(id) AS ("
            "SELECT id FROM category WHERE id = ? "
            "UNION ALL SELECT c.id FROM category c "
            "JOIN subtree ON c.parent_id = subtree.id"
            ") SELECT COUNT(*) - 1 AS descendants, "
            "(SELECT COUNT(*) FROM snippet WHERE category_id IN "
            "(SELECT id FROM subtree)) AS snippets FROM subtree",
            (id,),
        ).fetchone()
        return row["descendants"], row["snippets"]

    def get_snippets(self, category_id: int, order_by_name: bool = False):
        """Yield snippets in a category, with higher weights first."""
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
        """Yield snippets whose name or content contains a literal term."""
        if not term:
            return  # An empty query deliberately yields no results.
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
        """Return one snippet or raise :class:`EntityNotFoundError`."""
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

    def category_exist(
        self,
        name_or_id: str | int,
        parent_id: int | None = None,
    ) -> int | None:
        """Return the matching category ID, or ``None`` when absent."""
        if isinstance(name_or_id, str):
            if parent_id is None:
                result = self._connection.execute(
                    "SELECT id FROM category WHERE name = ? COLLATE NOCASE "
                    "AND parent_id IS NULL",
                    (name_or_id,),
                )
            else:
                result = self._connection.execute(
                    "SELECT id FROM category WHERE name = ? COLLATE NOCASE "
                    "AND parent_id = ?",
                    (name_or_id, parent_id),
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
        """Return the matching snippet ID, or ``None`` when absent."""
        if category_id is not None:
            result = self._connection.execute(
                "SELECT id FROM snippet "
                "WHERE name = ? COLLATE NOCASE AND category_id = ?",
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
        """Validate, persist, and publish a new category."""
        self.validate_category(category)
        if self.category_exist(category.name, category.parent_id):
            raise CategoryValidationError(
                "A category with this name already exists at this level"
            )
        with self._connection as c:
            result = c.execute(
                "INSERT INTO category (parent_id, name) VALUES (?, ?)",
                (category.parent_id, category.name),
            )
            category.id = result.lastrowid
        self.ee.emit("category.added", category)
        return category

    def edit_category(self, category: Category) -> Category:
        """Validate and persist changes to an existing category."""
        # Check that category exists:
        if category.id is None:
            raise CategoryValidationError("The category has no ID")
        self.get_category(category.id)
        self.validate_category(category)
        existing_id = self.category_exist(category.name, category.parent_id)
        if existing_id is not None and existing_id != category.id:
            raise CategoryValidationError(
                "A category with this name already exists at this level"
            )
        with self._connection as c:
            c.execute(
                "UPDATE category SET parent_id = ?, name = ? WHERE id = ?",
                (
                    category.parent_id,
                    category.name,
                    category.id
                ),
            )
        self.ee.emit("category.edited", category)
        return category

    def validate_category(self, category: Category) -> None:
        """Normalize a category and enforce tree invariants."""
        category.name = self._normalize_name(
            category.name,
            CategoryValidationError,
        )
        if category.parent_id is not None:
            if not self.category_exist(category.parent_id):
                raise CategoryValidationError("The parent category does not exist")
            if category.id == category.parent_id:
                raise CategoryValidationError(
                    "A category cannot be its own parent"
                )
            if category.id is not None and self._is_category_descendant(
                category.parent_id,
                category.id,
            ):
                raise CategoryValidationError(
                    "A category cannot be moved below one of its descendants"
                )

    def _is_category_descendant(self, id: int, possible_ancestor_id: int) -> bool:
        """Return whether ``id`` is at or below ``possible_ancestor_id``."""
        row = self._connection.execute(
            "WITH RECURSIVE ancestors(id, parent_id) AS ("
            "SELECT id, parent_id FROM category WHERE id = ? "
            "UNION ALL SELECT c.id, c.parent_id FROM category c "
            "JOIN ancestors ON c.id = ancestors.parent_id"
            ") SELECT 1 FROM ancestors WHERE id = ?",
            (id, possible_ancestor_id),
        ).fetchone()
        return row is not None

    def move_category(self, id: int, parent_id: int | None) -> Category:
        """Move a category subtree below a new parent."""
        category = self.get_category(id)
        category.parent_id = parent_id
        return self.edit_category(category)

    def copy_category(self, id: int, parent_id: int | None) -> Category:
        """Deep-copy a category, its descendants, and their snippets."""
        source = self.get_category(id)
        if parent_id is not None and self._is_category_descendant(parent_id, id):
            raise CategoryValidationError(
                "A category cannot be copied into itself or one of its descendants"
            )
        copied = Category(name=source.name, parent_id=parent_id)
        with self._connection as c:
            self.validate_category(copied)
            if self.category_exist(copied.name, copied.parent_id):
                raise CategoryValidationError(
                    "A category with this name already exists at this level"
                )
            copied.id = c.execute(
                "INSERT INTO category (parent_id, name) VALUES (?, ?)",
                (copied.parent_id, copied.name),
            ).lastrowid
            self._copy_category_contents(c, source.id, copied.id)
        self.ee.emit("category.added", copied)
        return copied

    def _copy_category_contents(
        self,
        connection,
        source_id: int,
        target_id: int,
    ) -> None:
        """Recursively copy child categories and snippets into a new parent."""
        connection.execute(
            "INSERT INTO snippet (category_id, name, content, weight) "
            "SELECT ?, name, content, weight FROM snippet WHERE category_id = ?",
            (target_id, source_id),
        )
        for child in self.get_category_children(source_id):
            new_child_id = connection.execute(
                "INSERT INTO category (parent_id, name) VALUES (?, ?)",
                (target_id, child.name),
            ).lastrowid
            self._copy_category_contents(connection, child.id, new_child_id)

    def delete_category(self, id: int) -> Category:
        """Delete a category and its complete subtree."""
        category = self.get_category(id)
        with self._connection as c:
            # Keep the operation safe even for databases created while foreign
            # key enforcement was disabled.
            c.execute("DELETE FROM snippet WHERE category_id = ?", (id,))
            c.execute("DELETE FROM category WHERE id = ?", (id,))
        self.ee.emit("category.deleted", id)
        return category

    def move_snippet(self, id: int, category_id: int) -> Snippet:
        """Move a snippet into another category."""
        return self.move_snippets((id,), category_id)[0]

    def copy_snippet(self, id: int, category_id: int) -> Snippet:
        """Copy a snippet into another category."""
        return self.copy_snippets((id,), category_id)[0]

    def move_snippets(
        self,
        ids: tuple[int, ...] | list[int],
        category_id: int,
    ) -> list[Snippet]:
        """Atomically move multiple snippets into another category."""
        snippets = [self.get_snippet(id) for id in ids]
        for snippet in snippets:
            snippet.category_id = category_id
            self.validate_snippet(snippet)
        with self._connection as c:
            c.executemany(
                "UPDATE snippet SET category_id = ? WHERE id = ?",
                ((category_id, snippet.id) for snippet in snippets),
            )
        for snippet in snippets:
            self.ee.emit("snippet.edited", snippet)
        return snippets

    def copy_snippets(
        self,
        ids: tuple[int, ...] | list[int],
        category_id: int,
    ) -> list[Snippet]:
        """Atomically copy multiple snippets into another category."""
        snippets = []
        for id in ids:
            source = self.get_snippet(id)
            snippet = Snippet(
                name=source.name,
                content=source.content,
                category_id=category_id,
                weight=source.weight,
            )
            self.validate_snippet(snippet)
            snippets.append(snippet)
        with self._connection as c:
            for snippet in snippets:
                snippet.id = c.execute(
                    "INSERT INTO snippet "
                    "(name, category_id, weight, content) VALUES (?, ?, ?, ?)",
                    (
                        snippet.name,
                        snippet.category_id,
                        snippet.weight,
                        snippet.content,
                    ),
                ).lastrowid
        for snippet in snippets:
            self.ee.emit("snippet.added", snippet)
        return snippets

    def validate_snippet(self, snippet: Snippet) -> None:
        """Normalize a snippet and enforce its domain constraints."""
        snippet.name = self._normalize_name(
            snippet.name,
            SnippetValidationError,
        )
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
        """Validate, persist, and publish a new snippet."""
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
        """Validate and persist changes to an existing snippet."""
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

    def delete_snippet(self, id: int) -> Snippet:
        """Delete and return an existing snippet."""
        return self.delete_snippets((id,))[0]

    def delete_snippets(
        self,
        ids: tuple[int, ...] | list[int],
    ) -> list[Snippet]:
        """Atomically delete and return multiple snippets."""
        snippets = [self.get_snippet(id) for id in ids]
        if not snippets:
            return []
        placeholders = ", ".join("?" for _snippet in snippets)
        with self._connection as c:
            c.execute(
                "DELETE FROM snippet WHERE id IN ({})".format(placeholders),
                tuple(snippet.id for snippet in snippets),
            )
        for snippet in snippets:
            self.ee.emit("snippet.deleted", snippet)
        return snippets

    def _has_table_column(self, table: str, column: str) -> bool:
        """Return whether a SQLite table contains a named column."""
        result = self._connection.execute(
            "SELECT COUNT(*) AS CNTREC FROM pragma_table_info(?) WHERE name=?",
            (table, column),
        )
        return result.fetchone()["CNTREC"] > 0

    def _get_table_names(self) -> set[str]:
        """Return all user-defined table names in the database."""
        rows = self._connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        return {row["name"] for row in rows}

    @staticmethod
    def _normalize_name(
        name: str,
        error_type: type[DataModelError],
    ) -> str:
        """Trim a name and raise the supplied error for empty values."""
        normalized_name = name.strip()
        if not normalized_name:
            raise error_type("The name must not be empty")
        return normalized_name

    def _escape_like(self, string: str) -> str:
        """Escape a literal string for use in a SQLite ``LIKE`` pattern."""
        # LIKE wildcards are user data here, not search-pattern syntax.
        return string.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def close(self) -> None:
        """Close the database connection; repeated calls are harmless."""
        if self._closed:
            return
        self._connection.close()
        self._closed = True
