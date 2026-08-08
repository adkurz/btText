import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platform_support import logging_support


class LoggingSupportTestCase(unittest.TestCase):
    @patch("platform_support.logging_support.open_path")
    def test_open_log_directory_creates_and_opens_directory(self, open_path):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory) / "logs"
            with patch.object(
                logging_support.app_paths,
                "get_log_directory",
                return_value=directory,
            ):
                result = logging_support.open_log_directory()

        self.assertEqual(result, directory)
        open_path.assert_called_once_with(directory)
