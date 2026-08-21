"""Play bundled application sounds through the native Windows API."""

import logging
import winsound

from platform_support import app_paths


logger = logging.getLogger(__name__)


def play_sound(filename: str) -> None:
    """Play a bundled WAV file asynchronously without disrupting the caller."""
    sound_file = app_paths.get_sounds_folder() / filename
    try:
        winsound.PlaySound(
            str(sound_file),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
        )
    except (OSError, RuntimeError):
        logger.warning(
            "Could not play bundled sound %s",
            sound_file,
            exc_info=True,
        )
