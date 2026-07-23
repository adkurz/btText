"""Application-local copy/cut state shared by category and snippet views."""

from dataclasses import dataclass


@dataclass
class Transfer:
    """Description of an application-local category or snippet transfer."""
    kind: str
    entity_id: int
    copy: bool


class TransferBuffer:
    """Hold one pending entity transfer without touching the OS clipboard."""

    def __init__(self):
        """Create an empty transfer buffer."""
        self.value: Transfer | None = None

    def set(self, kind: str, entity_id: int, copy: bool) -> None:
        """Store an entity and whether the pending operation is a copy."""
        self.value = Transfer(kind, entity_id, copy)

    def clear(self) -> None:
        """Discard the pending transfer."""
        self.value = None
