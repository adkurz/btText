"""Tests for native playback of bundled application sounds."""

import unittest
from pathlib import Path
from unittest.mock import patch

from platform_support import sounds


class SoundsTests(unittest.TestCase):
    @patch("platform_support.sounds.winsound.PlaySound")
    @patch("platform_support.sounds.app_paths.get_sounds_folder")
    def test_sound_is_played_asynchronously(self, get_sounds_folder, play_sound):
        get_sounds_folder.return_value = Path("bundled-sounds")

        sounds.play_sound("confirmation.wav")

        play_sound.assert_called_once_with(
            str(Path("bundled-sounds") / "confirmation.wav"),
            sounds.winsound.SND_FILENAME
            | sounds.winsound.SND_ASYNC
            | sounds.winsound.SND_NODEFAULT,
        )

    @patch("platform_support.sounds.logger.warning")
    @patch(
        "platform_support.sounds.winsound.PlaySound",
        side_effect=RuntimeError("unavailable"),
    )
    def test_playback_failure_is_logged_without_escaping(self, play_sound, warning):
        sounds.play_sound("missing.wav")

        play_sound.assert_called_once()
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
