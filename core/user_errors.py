"""Structured errors that can be localized at a user-interface boundary."""

from typing import Any


class UserFacingError(Exception):
    """Carry a stable error code and formatting parameters across layers."""

    def __init__(
        self,
        code: str,
        debug_message: str,
        **parameters: Any,
    ):
        """Create an error with an English diagnostic representation."""
        self.code = code
        self.parameters = parameters
        super().__init__(debug_message.format(**parameters))
