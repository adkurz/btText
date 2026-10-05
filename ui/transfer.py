"""Application-local category and snippet transfer orchestration."""

from dataclasses import dataclass
from typing import Literal, assert_never

from core import datamodel


TransferKind = Literal["category", "snippet"]
_TRANSFER_KINDS = frozenset(("category", "snippet"))


def _normalize_entity_ids(
    entity_ids: int | list[int] | tuple[int, ...],
) -> tuple[int, ...]:
    """Return a non-empty immutable collection of entity IDs."""
    normalized = (entity_ids,) if isinstance(entity_ids, int) else tuple(entity_ids)
    if not normalized:
        raise ValueError("A transfer must contain at least one entity")
    return normalized


@dataclass
class Transfer:
    """Description of an application-local category or snippet transfer."""

    kind: TransferKind
    entity_ids: tuple[int, ...]
    copy: bool

    def __post_init__(self) -> None:
        """Reject unsupported transfer kinds at the construction boundary."""
        if self.kind not in _TRANSFER_KINDS:
            raise ValueError(f"Unsupported transfer kind: {self.kind!r}")

    @property
    def entity_id(self) -> int:
        """Return the sole entity ID used by category transfers."""
        if len(self.entity_ids) != 1:
            raise ValueError("The transfer contains more than one entity")
        return self.entity_ids[0]


class TransferBuffer:
    """Hold one pending entity transfer without touching the OS clipboard."""

    def __init__(self, model: datamodel.DataModel):
        """Create a buffer whose sources are invalidated by model deletions."""
        self.value: Transfer | None = None
        self._model = model
        model.ee.on("category.deleted", self._on_category_deleted)
        model.ee.on("snippet.deleted", self._on_snippet_deleted)

    def set(
        self,
        kind: TransferKind,
        entity_ids: int | list[int] | tuple[int, ...],
        copy: bool,
    ) -> None:
        """Store one or more entities and the pending operation."""
        self.value = Transfer(kind, _normalize_entity_ids(entity_ids), copy)

    def clear(self) -> None:
        """Discard the pending transfer."""
        self.value = None

    def _on_category_deleted(self, category_id: int) -> None:
        """Discard sources removed anywhere in a deleted category subtree."""
        transfer = self.value
        if transfer is None:
            return
        exists = (
            self._model.category_exist
            if transfer.kind == "category"
            else self._model.snippet_exist
        )
        try:
            # Deletion events run synchronously after commit, before a later
            # insertion can reuse an ID. A missing member invalidates the
            # entire transfer instead of silently transferring a partial batch.
            if any(exists(entity_id) is None for entity_id in transfer.entity_ids):
                self.clear()
        except datamodel.DataModelError:
            # A failed lookup cannot establish that the sources survived.
            self.clear()
            raise

    def _on_snippet_deleted(self, snippet: datamodel.Snippet) -> None:
        """Discard the whole transfer when one staged snippet was deleted."""
        transfer = self.value
        if (
            transfer is not None
            and transfer.kind == "snippet"
            and snippet.id in transfer.entity_ids
        ):
            self.clear()


@dataclass(frozen=True)
class TransferResult:
    """Entities returned by one successfully applied transfer."""

    transfer: Transfer
    category: datamodel.Category | None = None
    snippets: tuple[datamodel.Snippet, ...] = ()


class TransferService:
    """Stage and apply transfers shared by the category and snippet views."""

    def __init__(
        self,
        model: datamodel.DataModel,
        buffer: TransferBuffer,
    ) -> None:
        """Coordinate model operations through one shared transfer buffer."""
        self._model = model
        self._buffer = buffer

    @property
    def pending(self) -> Transfer | None:
        """Return the currently staged transfer, if any."""
        return self._buffer.value

    def stage(
        self,
        kind: TransferKind,
        entity_ids: int | list[int] | tuple[int, ...],
        copy: bool,
    ) -> Transfer:
        """Stage a copy or cut operation and return its normalized value."""
        self._buffer.set(kind, entity_ids, copy)
        assert self._buffer.value is not None
        return self._buffer.value

    def apply_pending(self, destination_id: int | None) -> TransferResult | None:
        """Apply the pending transfer and clear a successful cut operation."""
        transfer = self.pending
        if transfer is None:
            return None

        result = self._apply(transfer, destination_id)
        if result is not None and not transfer.copy:
            self._buffer.clear()
        return result

    def execute(
        self,
        kind: TransferKind,
        entity_ids: int | list[int] | tuple[int, ...],
        destination_id: int | None,
        copy: bool,
    ) -> TransferResult | None:
        """Apply an unstaged transfer without changing the shared buffer."""
        transfer = Transfer(kind, _normalize_entity_ids(entity_ids), copy)
        return self._apply(transfer, destination_id)

    def _apply(
        self,
        transfer: Transfer,
        destination_id: int | None,
    ) -> TransferResult | None:
        """Route one explicit transfer to the corresponding model operation."""

        if transfer.kind == "category":
            if transfer.copy:
                category = self._model.copy_category(
                    transfer.entity_id,
                    destination_id,
                )
            else:
                category = self._model.move_category(
                    transfer.entity_id,
                    destination_id,
                )
            result = TransferResult(transfer, category=category)
        elif transfer.kind == "snippet":
            if transfer.copy:
                snippets = self._model.copy_snippets(
                    transfer.entity_ids,
                    destination_id,
                )
            else:
                snippets = self._model.move_snippets(
                    transfer.entity_ids,
                    destination_id,
                )
            result = TransferResult(transfer, snippets=tuple(snippets))
        else:
            assert_never(transfer.kind)
        return result
