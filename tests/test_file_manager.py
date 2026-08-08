import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platform_support import file_manager


class FileManagerTestCase(unittest.TestCase):
    @patch("platform_support.file_manager.os.startfile", create=True)
    def test_open_containing_directory_opens_resolved_parent(self, startfile):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "data.db"
            result = file_manager.open_containing_directory(database_file)

        self.assertEqual(result, database_file.resolve().parent)
        startfile.assert_called_once_with(database_file.resolve().parent)
