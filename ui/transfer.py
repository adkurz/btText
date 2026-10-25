"""Application-local category and snippet transfer orchestration."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import secrets
from typing import Literal, assert_never

from core import datamodel


TransferKind = Literal["category", "snippet"]
_TRANSFER_KINDS = frozenset(("category", "snippet"))
DRAG_TOKEN_BYTES = 32


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
        self._drag_token: bytes | None = None
        self._drag_transfer: Transfer | None = None
        self._model = model
        model.ee.on("category.deleted", self._on_category_deleted)
        model.ee.on("snippets.deleted", self._on_snippets_deleted)

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

    @property
    def has_drag(self) -> bool:
        """Return whether an internal drag can still be consumed."""
        return self._drag_transfer is not None

    @contextmanager
    def dragging(self, kind: TransferKind, entity_id: int) -> Iterator[bytes]:
        """Authorize one move only for the lifetime of its native drag loop."""
        transfer = Transfer(kind, (entity_id,), copy=False)
        token = secrets.token_bytes(DRAG_TOKEN_BYTES)
        self._drag_token = token
        self._drag_transfer = transfer
        try:
            yield token
        finally:
            if self._drag_token == token:
                self._clear_drag()

    def take_drag(self, token: bytes) -> Transfer | None:
        """Consume an active drag without accepting serialized entity IDs."""
        if self._drag_token is None or token != self._drag_token:
            return None
        transfer = self._drag_transfer
        self._clear_drag()
        return transfer

    def _clear_drag(self) -> None:
        """Invalidate the current drag without touching copied or cut items."""
        self._drag_token = None
        self._drag_transfer = None

    def _on_category_deleted(self, category_id: int) -> None:
        """Discard sources removed anywhere in a deleted category subtree."""
        try:
            for transfer in (self.value, self._drag_transfer):
                if transfer is None:
                    continue
                exists = (
                    self._model.category_exist
                    if transfer.kind == "category"
                    else self._model.snippet_exist
                )
                # Check synchronously after deletion, before an ID can be reused.
                if any(exists(entity_id) is None for entity_id in transfer.entity_ids):
                    if transfer is self.value:
                        self.clear()
                    if transfer is self._drag_transfer:
                        self._clear_drag()
        except datamodel.DataModelError:
            # A failed lookup cannot establish that the sources survived.
            self.clear()
            self._clear_drag()
            raise

    def _on_snippets_deleted(self, snippets: tuple[datamodel.Snippet, ...]) -> None:
        """Discard a whole transfer when any source in the batch was deleted."""
        deleted_ids = {snippet.id for snippet in snippets}
        for transfer in (self.value, self._drag_transfer):
            if (
                transfer is not None
                and transfer.kind == "snippet"
                and deleted_ids.intersection(transfer.entity_ids)
            ):
                if transfer is self.value:
                    self.clear()
                if transfer is self._drag_transfer:
                    self._clear_drag()


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
