"""Application-local copy/cut state shared by category and snippet views."""

from dataclasses import dataclass


@dataclass
class Transfer:
    """Description of an application-local category or snippet transfer."""
    kind: str
    entity_ids: tuple[int, ...]
    copy: bool

    @property
    def entity_id(self) -> int:
        """Return the sole entity ID used by category transfers."""
        if len(self.entity_ids) != 1:
            raise ValueError("The transfer contains more than one entity")
        return self.entity_ids[0]


class TransferBuffer:
    """Hold one pending entity transfer without touching the OS clipboard."""

    def __init__(self):
        """Create an empty transfer buffer."""
        self.value: Transfer | None = None

    def set(
        self,
        kind: str,
        entity_ids: int | list[int] | tuple[int, ...],
        copy: bool,
    ) -> None:
        """Store one or more entities and the pending operation."""
        if isinstance(entity_ids, int):
            entity_ids = (entity_ids,)
        else:
            entity_ids = tuple(entity_ids)
        if not entity_ids:
            raise ValueError("A transfer must contain at least one entity")
        self.value = Transfer(kind, entity_ids, copy)

    def clear(self) -> None:
        """Discard the pending transfer."""
        self.value = None
