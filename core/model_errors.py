"""Domain errors raised by the data model."""

from core.user_errors import UserFacingError


class DataModelError(UserFacingError):
    """Base class for errors that can be shown to the user."""


class EntityNotFoundError(DataModelError):
    """Raised when an operation refers to an entity that no longer exists."""


class CategoryValidationError(DataModelError):
    """Raised when a category violates naming or tree constraints."""


class SnippetValidationError(DataModelError):
    """Raised when a snippet violates naming, weight, or category constraints."""
