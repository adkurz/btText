"""Persistence and domain operations for categories and text snippets."""

import dataclasses
import functools
import inspect
import sqlite3
from pathlib import Path

from core.database_schema import (
    SCHEMA_VERSION as DATABASE_SCHEMA_VERSION,
    create_current_schema,
)
from core.events import EventEmitter
from core.model_errors import (
    CategoryValidationError,
    DataModelError,
    EntityNotFoundError,
    SnippetValidationError,
)
from core.migrations import get_database_version, migrate_database


def _translate_sqlite_errors(method):
    """Translate unexpected runtime SQLite failures at the model boundary."""
    if inspect.isgeneratorfunction(method):

        @functools.wraps(method)
        def generator_wrapper(*args, **kwargs):
            try:
                yield from method(*args, **kwargs)
            except sqlite3.Error as error:
                raise DataModelError(
                    "database_operation_failed",
                    "The database operation failed: {reason}",
                    reason=error,
                ) from error

        return generator_wrapper

    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except sqlite3.Error as error:
            raise DataModelError(
                "database_operation_failed",
                "The database operation failed: {reason}",
                reason=error,
            ) from error

    return wrapper


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
    id: int | None = None
    hotstring: str | None = None


@dataclasses.dataclass
class Category:
    """A persisted node in the category tree."""

    name: str
    id: int | None = None
    parent_id: int | None = None


@dataclasses.dataclass(frozen=True)
class CategorySummary:
    """A category projection with its direct snippet count."""

    category: Category
    number_of_snippets: int


class DataModel:
    """Manage the category tree and snippets stored in a SQLite database.

    Mutations commit before publishing model events, allowing listeners to
    reload entities without observing a partially applied transaction.
    """

    WEIGHTS = (1, 2, 3)
    SCHEMA_VERSION = DATABASE_SCHEMA_VERSION

    def __init__(
        self,
        ee: EventEmitter,
        db_file: str | Path,
        *,
        allow_create: bool = True,
    ):
        """Open, validate, and if necessary migrate the SQLite database."""
        self.ee = ee
        self._closed = False
        db_file = Path(db_file)
        exists = db_file.exists()
        if not allow_create and not exists:
            raise DataModelError(
                "database_file_missing",
                "The selected database file does not exist.",
            )
        self._connection = None
        try:
            # Foreign-key enforcement must be enabled outside a transaction.
            self._connection = sqlite3.connect(db_file, autocommit=True)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            foreign_keys_enabled = self._connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0]
            if not foreign_keys_enabled:
                raise DataModelError(
                    "database_foreign_keys_unavailable",
                    "Could not enable SQLite foreign-key support",
                )
            self._connection.autocommit = False
            tables = self._get_table_names()
            if not exists or (allow_create and not tables):
                self.create_tables()
            else:
                missing_tables = {"category", "snippet"} - tables
                if missing_tables:
                    raise DataModelError(
                        "database_schema_incomplete",
                        "The database schema is incomplete. Missing table(s): "
                        "{missing_tables}",
                        missing_tables=", ".join(sorted(missing_tables)),
                    )
                self._migrate_database()
            self._validate_database_integrity()
        except DataModelError:
            if self._connection is not None:
                self._connection.close()
            self._closed = True
            raise
        except sqlite3.Error as error:
            if self._connection is not None:
                self._connection.close()
            self._closed = True
            raise DataModelError(
                "database_open_failed",
                "The database could not be opened: {reason}",
                reason=error,
            ) from error

    def create_tables(self):
        """Create the current schema in a new or empty database."""
        create_current_schema(self._connection)

    def _migrate_database(self) -> None:
        """Apply each schema migration exactly once and in version order."""
        migrate_database(self._connection)

    def _get_database_version(self) -> int:
        """Return SQLite's application-defined schema version."""
        return get_database_version(self._connection)

    def _validate_database_integrity(self) -> None:
        """Reject broken foreign keys and cycles in the category hierarchy."""
        foreign_key_violation = self._connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchone()
        if foreign_key_violation is not None:
            raise DataModelError(
                "database_foreign_key_violation",
                "The database contains records with invalid relationships",
            )

        category_cycle = self._connection.execute(
            "WITH RECURSIVE ancestors(start_id, ancestor_id) AS ("
            "SELECT id, parent_id FROM category WHERE parent_id IS NOT NULL "
            "UNION "
            "SELECT ancestors.start_id, category.parent_id "
            "FROM ancestors JOIN category "
            "ON category.id = ancestors.ancestor_id "
            "WHERE category.parent_id IS NOT NULL"
            ") SELECT 1 FROM ancestors "
            "WHERE start_id = ancestor_id LIMIT 1"
        ).fetchone()
        if category_cycle is not None:
            raise DataModelError(
                "database_category_cycle",
                "The database contains a cycle in the category hierarchy",
            )

    @_translate_sqlite_errors
    def get_category(self, id: int) -> Category:
        """Return one category or raise :class:`EntityNotFoundError`."""
        result = self._connection.execute(
            "SELECT id, parent_id, name FROM category WHERE id = :id",
            {"id": id},
        )
        category = result.fetchone()
        if category is None:
            raise EntityNotFoundError(
                "category_not_found",
                "Category with ID {id} does not exist",
                id=id,
            )
        return Category(
            id=category["id"],
            parent_id=category["parent_id"],
            name=category["name"],
        )

    @_translate_sqlite_errors
    def get_categories(
        self,
        order: bool = False,
        parent_id: int | None = None,
        all_categories: bool = True,
    ):
        """Yield persisted categories, optionally limited to direct children."""
        sql = "SELECT id, parent_id, name FROM category"
        parameters = ()
        if not all_categories:
            if parent_id is None:
                sql += " WHERE parent_id IS NULL"
            else:
                sql += " WHERE parent_id = ?"
                parameters = (parent_id,)
        if order:
            sql += " ORDER BY name COLLATE NOCASE, id"
        for category in self._connection.execute(sql, parameters):
            yield Category(
                id=category["id"],
                parent_id=category["parent_id"],
                name=category["name"],
            )

    @_translate_sqlite_errors
    def get_category_summaries(
        self,
        order: bool = False,
        parent_id: int | None = None,
        all_categories: bool = True,
    ):
        """Yield category projections with direct snippet counts."""
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
            sql += " ORDER BY name COLLATE NOCASE, id"
        for row in self._connection.execute(sql, parameters):
            yield CategorySummary(
                category=Category(
                    id=row["id"],
                    parent_id=row["parent_id"],
                    name=row["name"],
                ),
                number_of_snippets=row["number_of_snippets"],
            )

    @_translate_sqlite_errors
    def get_all_category_summaries(self) -> tuple[CategorySummary, ...]:
        """Return all category summaries in one query for tree construction."""
        return tuple(self.get_category_summaries())

    @_translate_sqlite_errors
    def get_category_children(self, parent_id: int | None):
        """Yield direct children of a category, ordered by name."""
        return self.get_categories(
            order=True,
            parent_id=parent_id,
            all_categories=False,
        )

    @_translate_sqlite_errors
    def get_category_child_summaries(self, parent_id: int | None):
        """Yield direct child projections ordered by category name."""
        return self.get_category_summaries(
            order=True,
            parent_id=parent_id,
            all_categories=False,
        )

    @_translate_sqlite_errors
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

    @_translate_sqlite_errors
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

    @_translate_sqlite_errors
    def get_snippets(self, category_id: int):
        """Yield snippets ordered by weight, name, and ID."""
        sql = (
            "SELECT id, category_id, name, weight, content, hotstring FROM snippet "
            "WHERE category_id = ? "
            "ORDER BY weight DESC, name COLLATE NOCASE, id"
        )
        for snippet in self._connection.execute(sql, (category_id,)):
            yield Snippet(
                id=snippet["id"],
                category_id=snippet["category_id"],
                name=snippet["name"],
                content=snippet["content"],
                weight=snippet["weight"],
                hotstring=snippet["hotstring"],
            )

    @_translate_sqlite_errors
    def search_snippets(self, term: str):
        """Yield snippets whose name or content contains a literal term."""
        if not term:
            return  # An empty query deliberately yields no results.
        sql = (
            "SELECT s.id, s.category_id, c.name AS category_name, s.name, "
            "s.weight, s.content, s.hotstring FROM snippet s "
            "INNER JOIN category c ON s.category_id = c.id "
            "WHERE s.name LIKE :term ESCAPE '\\' "
            "OR s.content LIKE :term ESCAPE '\\' "
            "ORDER BY category_name COLLATE NOCASE, c.id, s.weight DESC, "
            "s.name COLLATE NOCASE, s.id"
        )
        for snippet in self._connection.execute(
            sql, {"term": "%" + self._escape_like(term) + "%"}
        ):
            yield Snippet(
                id=snippet["id"],
                category_id=snippet["category_id"],
                name=snippet["name"],
                content=snippet["content"],
                weight=snippet["weight"],
                hotstring=snippet["hotstring"],
            )

    @_translate_sqlite_errors
    def get_snippet(self, id: int) -> Snippet:
        """Return one snippet or raise :class:`EntityNotFoundError`."""
        result = self._connection.execute(
            "SELECT id, category_id, name, weight, content, hotstring "
            "FROM snippet WHERE id = ?",
            (id,),
        )
        snippet = result.fetchone()
        if snippet is None:
            raise EntityNotFoundError(
                "snippet_not_found",
                "Snippet with ID {id} does not exist",
                id=id,
            )
        return Snippet(
            id=snippet["id"],
            category_id=snippet["category_id"],
            name=snippet["name"],
            content=snippet["content"],
            weight=snippet["weight"],
            hotstring=snippet["hotstring"],
        )

    @_translate_sqlite_errors
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

    @_translate_sqlite_errors
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

    @_translate_sqlite_errors
    def add_category(self, category: Category) -> Category:
        """Validate, persist, and publish a new category."""
        self.validate_category(category)
        if self.category_exist(category.name, category.parent_id):
            raise CategoryValidationError(
                "category_name_duplicate",
                "A category with this name already exists at this level",
            )
        try:
            with self._connection as c:
                result = c.execute(
                    "INSERT INTO category (parent_id, name) VALUES (?, ?)",
                    (category.parent_id, category.name),
                )
                category.id = result.lastrowid
        except sqlite3.IntegrityError as error:
            self._raise_category_integrity_error(error)
        self.ee.emit("category.added", category)
        return category

    @_translate_sqlite_errors
    def edit_category(self, category: Category) -> Category:
        """Validate and persist changes to an existing category."""
        # Check that category exists:
        if category.id is None:
            raise CategoryValidationError(
                "category_id_missing",
                "The category has no ID",
            )
        self.get_category(category.id)
        self.validate_category(category)
        existing_id = self.category_exist(category.name, category.parent_id)
        if existing_id is not None and existing_id != category.id:
            raise CategoryValidationError(
                "category_name_duplicate",
                "A category with this name already exists at this level",
            )
        try:
            with self._connection as c:
                c.execute(
                    "UPDATE category SET parent_id = ?, name = ? WHERE id = ?",
                    (category.parent_id, category.name, category.id),
                )
        except sqlite3.IntegrityError as error:
            self._raise_category_integrity_error(error)
        self.ee.emit("category.edited", category)
        return category

    @_translate_sqlite_errors
    def validate_category(self, category: Category) -> None:
        """Normalize a category and enforce tree invariants."""
        category.name = self._normalize_name(
            category.name,
            CategoryValidationError,
        )
        if category.parent_id is not None:
            if not self.category_exist(category.parent_id):
                raise CategoryValidationError(
                    "category_parent_missing",
                    "The parent category does not exist",
                )
            if category.id == category.parent_id:
                raise CategoryValidationError(
                    "category_own_parent",
                    "A category cannot be its own parent",
                )
            if category.id is not None and self._is_category_descendant(
                category.parent_id,
                category.id,
            ):
                raise CategoryValidationError(
                    "category_move_into_descendant",
                    "A category cannot be moved below one of its descendants",
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

    @_translate_sqlite_errors
    def move_category(self, id: int, parent_id: int | None) -> Category:
        """Move a category subtree below a new parent."""
        category = self.get_category(id)
        category.parent_id = parent_id
        return self.edit_category(category)

    @_translate_sqlite_errors
    def copy_category(self, id: int, parent_id: int | None) -> Category:
        """Deep-copy a category tree without globally unique hotstrings."""
        source = self.get_category(id)
        if parent_id is not None and self._is_category_descendant(parent_id, id):
            raise CategoryValidationError(
                "category_copy_into_descendant",
                "A category cannot be copied into itself or one of its descendants",
            )
        copied = Category(name=source.name, parent_id=parent_id)
        try:
            with self._connection as c:
                self.validate_category(copied)
                if self.category_exist(copied.name, copied.parent_id):
                    raise CategoryValidationError(
                        "category_name_duplicate",
                        "A category with this name already exists at this level",
                    )
                copied.id = c.execute(
                    "INSERT INTO category (parent_id, name) VALUES (?, ?)",
                    (copied.parent_id, copied.name),
                ).lastrowid
                self._copy_category_contents(c, source.id, copied.id)
        except sqlite3.IntegrityError as error:
            self._raise_category_integrity_error(error)
        self.ee.emit("category.added", copied)
        return copied

    def _copy_category_contents(
        self,
        connection,
        source_id: int,
        target_id: int,
    ) -> None:
        """Recursively copy children and snippets, omitting hotstrings."""
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

    @_translate_sqlite_errors
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

    @_translate_sqlite_errors
    def move_snippet(self, id: int, category_id: int) -> Snippet:
        """Move a snippet into another category."""
        return self.move_snippets((id,), category_id)[0]

    @_translate_sqlite_errors
    def copy_snippet(self, id: int, category_id: int) -> Snippet:
        """Copy a snippet without its globally unique hotstring."""
        return self.copy_snippets((id,), category_id)[0]

    @_translate_sqlite_errors
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
        try:
            with self._connection as c:
                c.executemany(
                    "UPDATE snippet SET category_id = ? WHERE id = ?",
                    ((category_id, snippet.id) for snippet in snippets),
                )
        except sqlite3.IntegrityError as error:
            self._raise_snippet_integrity_error(error)
        for snippet in snippets:
            self.ee.emit("snippet.edited", snippet)
        return snippets

    @_translate_sqlite_errors
    def copy_snippets(
        self,
        ids: tuple[int, ...] | list[int],
        category_id: int,
    ) -> list[Snippet]:
        """Atomically copy snippets without their globally unique hotstrings."""
        snippets = []
        for id in ids:
            source = self.get_snippet(id)
            snippet = Snippet(
                name=source.name,
                content=source.content,
                category_id=category_id,
                weight=source.weight,
                hotstring=None,
            )
            self.validate_snippet(snippet)
            snippets.append(snippet)
        try:
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
        except sqlite3.IntegrityError as error:
            self._raise_snippet_integrity_error(error)
        for snippet in snippets:
            self.ee.emit("snippet.added", snippet)
        return snippets

    @_translate_sqlite_errors
    def validate_snippet(self, snippet: Snippet) -> None:
        """Normalize a snippet and enforce its domain constraints."""
        snippet.name = self._normalize_name(
            snippet.name,
            SnippetValidationError,
        )
        # Check  that the content isn't empty:
        if snippet.content == "":
            raise SnippetValidationError(
                "snippet_content_empty",
                "The content must not be empty",
            )
        # Check that category id exists:
        if not self.category_exist(snippet.category_id):
            raise SnippetValidationError(
                "snippet_category_missing",
                "This category doesn't exist",
            )
        # Check that name in the same category doesn't exist:
        old_id = self.snippet_exist(snippet.name, snippet.category_id)
        id = snippet.id
        if old_id is not None and id != old_id:
            raise SnippetValidationError(
                "snippet_name_duplicate",
                "There is already a snippet with this name in this category",
            )
        # Check that weight is in the allowed range:
        if snippet.weight not in self.WEIGHTS:
            raise SnippetValidationError(
                "snippet_weight_invalid",
                "The weight isn't in the allowed range.",
            )
        if snippet.hotstring is not None:
            snippet.hotstring = snippet.hotstring.strip()
            if not snippet.hotstring:
                snippet.hotstring = None
            elif any(character.isspace() for character in snippet.hotstring):
                raise SnippetValidationError(
                    "snippet_hotstring_whitespace",
                    "The hotstring must not contain whitespace",
                )
            existing_id = self.hotstring_exist(snippet.hotstring)
            if existing_id is not None and existing_id != snippet.id:
                raise SnippetValidationError(
                    "snippet_hotstring_duplicate",
                    "This hotstring is already assigned to another snippet",
                )

    @_translate_sqlite_errors
    def add_snippet(self, snippet: Snippet) -> Snippet:
        """Validate, persist, and publish a new snippet."""
        self.validate_snippet(snippet)
        try:
            with self._connection as c:
                result = c.execute(
                    "INSERT INTO snippet "
                    "(name, category_id, weight, content, hotstring) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        snippet.name,
                        snippet.category_id,
                        snippet.weight,
                        snippet.content,
                        snippet.hotstring,
                    ),
                )
        except sqlite3.IntegrityError as error:
            self._raise_snippet_integrity_error(error)
        snippet.id = result.lastrowid
        self.ee.emit("snippet.added", snippet)
        return snippet

    @_translate_sqlite_errors
    def edit_snippet(self, snippet: Snippet) -> Snippet:
        """Validate and persist changes to an existing snippet."""
        # Check that snippet id exists:
        if snippet.id is None:
            raise SnippetValidationError(
                "snippet_id_missing",
                "The snippet has no ID",
            )
        self.get_snippet(snippet.id)
        self.validate_snippet(snippet)
        try:
            with self._connection as c:
                c.execute(
                    "UPDATE snippet SET name = ?, category_id = ?, "
                    "weight = ?, content = ?, hotstring = ? WHERE id = ?",
                    (
                        snippet.name,
                        snippet.category_id,
                        snippet.weight,
                        snippet.content,
                        snippet.hotstring,
                        snippet.id,
                    ),
                )
        except sqlite3.IntegrityError as error:
            self._raise_snippet_integrity_error(error)
        self.ee.emit("snippet.edited", snippet)
        return snippet

    @_translate_sqlite_errors
    def delete_snippet(self, id: int) -> Snippet:
        """Delete and return an existing snippet."""
        return self.delete_snippets((id,))[0]

    @_translate_sqlite_errors
    def hotstring_exist(self, hotstring: str) -> int | None:
        """Return the snippet ID assigned to ``hotstring``, if any."""
        row = self._connection.execute(
            "SELECT id FROM snippet WHERE hotstring = ?",
            (hotstring,),
        ).fetchone()
        return row["id"] if row is not None else None

    @_translate_sqlite_errors
    def get_hotstring_snippets(self) -> tuple[Snippet, ...]:
        """Return all snippets that have an expansion hotstring."""
        rows = self._connection.execute(
            "SELECT id, category_id, name, weight, content, hotstring "
            "FROM snippet WHERE hotstring IS NOT NULL "
            "ORDER BY length(hotstring) DESC, id"
        )
        return tuple(
            Snippet(
                id=row["id"],
                category_id=row["category_id"],
                name=row["name"],
                weight=row["weight"],
                content=row["content"],
                hotstring=row["hotstring"],
            )
            for row in rows
        )

    @_translate_sqlite_errors
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

    @staticmethod
    def _raise_category_integrity_error(error: sqlite3.IntegrityError) -> None:
        """Translate expected category constraints into domain errors."""
        error_code = getattr(error, "sqlite_errorcode", None)
        if error_code == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
            raise CategoryValidationError(
                "category_name_duplicate",
                "A category with this name already exists at this level",
            ) from error
        if error_code == sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY:
            raise CategoryValidationError(
                "category_parent_missing",
                "The parent category does not exist",
            ) from error
        if error_code == sqlite3.SQLITE_CONSTRAINT_CHECK:
            raise CategoryValidationError(
                "category_own_parent",
                "A category cannot be its own parent",
            ) from error
        raise error

    @staticmethod
    def _raise_snippet_integrity_error(error: sqlite3.IntegrityError) -> None:
        """Translate expected snippet constraints into domain errors."""
        error_code = getattr(error, "sqlite_errorcode", None)
        if error_code == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
            if "hotstring" in str(error).lower():
                raise SnippetValidationError(
                    "snippet_hotstring_duplicate",
                    "This hotstring is already assigned to another snippet",
                ) from error
            raise SnippetValidationError(
                "snippet_name_duplicate",
                "There is already a snippet with this name in this category",
            ) from error
        if error_code == sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY:
            raise SnippetValidationError(
                "snippet_category_missing",
                "This category doesn't exist",
            ) from error
        if error_code == sqlite3.SQLITE_CONSTRAINT_CHECK:
            raise SnippetValidationError(
                "snippet_weight_invalid",
                "The weight isn't in the allowed range.",
            ) from error
        raise error

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
            raise error_type(
                "entity_name_empty",
                "The name must not be empty",
            )
        return normalized_name

    def _escape_like(self, string: str) -> str:
        """Escape a literal string for use in a SQLite ``LIKE`` pattern."""
        # LIKE wildcards are user data here, not search-pattern syntax.
        return string.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @_translate_sqlite_errors
    def close(self) -> None:
        """Close the database connection; repeated calls are harmless."""
        if self._closed:
            return
        self._connection.close()
        self._closed = True
