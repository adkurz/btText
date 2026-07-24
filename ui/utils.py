"""Small UI helpers shared by dialogs and list controls."""

from contextlib import contextmanager

from i18n import pgettext


@contextmanager
def managed_dialog(dialog):
    """Destroy a wx dialog reliably after its modal interaction."""
    try:
        yield dialog
    finally:
        dialog.Destroy()


def get_weight_string(weight: int) -> str:
    """Return the human-readable label for a snippet weight."""
    weights = {
        # Translators: Lowest search-ranking weight assigned to a snippet.
        1: pgettext("snippet weight", "Low"),
        # Translators: Medium search-ranking weight assigned to a snippet.
        2: pgettext("snippet weight", "Middle"),
        # Translators: Highest search-ranking weight assigned to a snippet.
        3: pgettext("snippet weight", "High"),
    }
    if not isinstance(weight, int):
        raise TypeError("weight has to be an integer")
    if weight not in weights:
        raise ValueError("Weight has to be an integer between 1 and 3")
    return weights[weight]


def reduce_string(string: str, length: int):
    """Truncate text to a fixed-length preview and append an ellipsis."""
    result = string[:length]
    if len(string) > length:
        result += "..."
    return result
