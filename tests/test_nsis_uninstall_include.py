"""Tests for the exact NSIS payload-removal include generator."""

import tempfile
import unittest
from pathlib import Path

from tools.build_nsis_uninstall_include import _nsis_path, build_uninstall_include


class NsisUninstallIncludeTests(unittest.TestCase):
    def test_generator_deletes_files_before_removing_deepest_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            application = Path(temporary_directory) / "btText"
            nested = application / "_internal" / "locale" / "de"
            nested.mkdir(parents=True)
            (application / "btText.exe").write_bytes(b"exe")
            (nested / "bttext.mo").write_bytes(b"catalog")

            include = build_uninstall_include(application)

        executable = 'Delete "$INSTDIR\\btText.exe"'
        catalog = 'Delete "$INSTDIR\\_internal\\locale\\de\\bttext.mo"'
        deepest = 'RMDir "$INSTDIR\\_internal\\locale\\de"'
        parent = 'RMDir "$INSTDIR\\_internal\\locale"'
        self.assertIn(executable, include)
        self.assertIn(catalog, include)
        self.assertLess(include.index(catalog), include.index(deepest))
        self.assertLess(include.index(deepest), include.index(parent))
        self.assertNotIn("RMDir /r", include)

    def test_generator_escapes_nsis_variable_and_quote_characters(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            application = Path(temporary_directory) / "btText"
            application.mkdir()
            (application / "price$.txt").write_bytes(b"value")

            include = build_uninstall_include(application)

        self.assertIn("price$$.txt", include)
        self.assertEqual(_nsis_path(Path('quoted"name')), 'quoted$\\"name')

    def test_empty_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "contains no files"):
                build_uninstall_include(Path(temporary_directory))


if __name__ == "__main__":
    unittest.main()
