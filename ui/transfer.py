from dataclasses import dataclass


@dataclass
class Transfer:
    kind: str
    entity_id: int
    copy: bool


class TransferBuffer:
    """Application-local copy/cut buffer used by mouse and keyboard actions."""

    def __init__(self):
        self.value: Transfer | None = None

    def set(self, kind: str, entity_id: int, copy: bool) -> None:
        self.value = Transfer(kind, entity_id, copy)

    def clear(self) -> None:
        self.value = None
