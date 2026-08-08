import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platform_support import shell


class ShellTestCase(unittest.TestCase):
    @patch("platform_support.shell.os.startfile", create=True)
    def test_open_path_opens_and_returns_resolved_path(self, startfile):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "document.html"
            result = shell.open_path(path)

        self.assertEqual(result, path.resolve())
        startfile.assert_called_once_with(path.resolve())

    @patch("platform_support.shell.open_path")
    def test_open_containing_directory_opens_resolved_parent(self, open_path):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "data.db"
            directory = database_file.resolve().parent
            open_path.return_value = directory

            result = shell.open_containing_directory(database_file)

        self.assertEqual(result, directory)
        open_path.assert_called_once_with(directory)
