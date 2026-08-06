"""Platform-independent matching of typed hotstrings."""

import string
import unicodedata
from collections.abc import Mapping
from typing import Generic, TypeVar

from core.user_errors import UserFacingError


class HotstringExpansionError(UserFacingError):
    """Raised when a recognized hotstring cannot be expanded in its target."""


Payload = TypeVar("Payload")


class HotstringMatcher(Generic[Payload]):
    """Track typed text and return configured payloads at boundaries."""

    def __init__(self):
        self._hotstrings: dict[str, Payload] = {}
        self._prefixes: set[str] = set()
        self._buffer = ""

    def update(self, hotstrings: Mapping[str, Payload]) -> None:
        """Replace the active case-sensitive trigger-to-payload mapping."""
        self._hotstrings = {
            trigger: payload
            for trigger, payload in hotstrings.items()
            if trigger
        }
        self._prefixes = {
            trigger[:length]
            for trigger in self._hotstrings
            for length in range(1, len(trigger) + 1)
        }
        self.reset()

    def reset(self) -> None:
        """Discard all remembered user input."""
        self._buffer = ""

    def backspace(self) -> None:
        """Mirror one user-generated Backspace in the internal buffer."""
        self._buffer = self._buffer[:-1]

    def character(self, character: str) -> Payload | None:
        """Record a character or return its payload when it is a boundary."""
        is_boundary = (
            character.isspace()
            or character in string.punctuation
            or unicodedata.category(character).startswith("P")
        )
        if is_boundary:
            payload = self._hotstrings.get(self._buffer)
            if payload is not None or character.isspace():
                self.reset()
                return payload
            candidate = self._buffer + character
            if candidate not in self._prefixes:
                self.reset()
                return None
        # Keep enough recent word text for Backspace to reveal a valid trigger
        # again without allowing an unbounded buffer.
        self._buffer = (self._buffer + character)[-256:]
        return None
