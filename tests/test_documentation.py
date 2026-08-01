"""Tests for documentation generation and localized manual selection."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platform_support import documentation
from tools.build_documentation import build_documentation, document_language


class DocumentationBuildTests(unittest.TestCase):
    """Verify recursive, standalone conversion of future Markdown files."""

    def test_all_markdown_files_are_converted_with_relative_paths(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            sources = root / "sources"
            output = root / "output"
            (sources / "nested").mkdir(parents=True)
            (sources / "manual-de.md").write_text(
                "# Handbuch\n\n[TOC]\n\n## Start\n\nText", encoding="utf-8"
            )
            (sources / "nested" / "guide.md").write_text(
                "# Guide\n\n```text\nexample\n```", encoding="utf-8"
            )

            outputs = build_documentation(sources, output)

            self.assertEqual(len(outputs), 2)
            german = (output / "manual-de.html").read_text(encoding="utf-8")
            nested = (output / "nested" / "guide.html").read_text(encoding="utf-8")
            self.assertIn('<html lang="de">', german)
            self.assertIn('<div class="toc">', german)
            self.assertIn("<pre><code", nested)

    def test_language_suffix_is_optional(self):
        self.assertEqual(document_language(Path("manual-de_DE.md")), "de-de")
        self.assertEqual(document_language(Path("setup.md")), "en")


class ManualSelectionTests(unittest.TestCase):
    """Verify exact, base-language, and English manual fallback."""

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        (self.directory / "manual-en.html").touch()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_exact_language_is_preferred(self):
        german = self.directory / "manual-de-de.html"
        german.touch()
        with patch.object(documentation, "get_documentation_directory", return_value=self.directory):
            self.assertEqual(documentation.get_manual_file("de_DE"), german)

    def test_base_language_precedes_english_fallback(self):
        german = self.directory / "manual-de.html"
        german.touch()
        with patch.object(documentation, "get_documentation_directory", return_value=self.directory):
            self.assertEqual(documentation.get_manual_file("de-AT"), german)

    def test_missing_language_falls_back_to_english(self):
        with patch.object(documentation, "get_documentation_directory", return_value=self.directory):
            self.assertEqual(
                documentation.get_manual_file("fr"),
                self.directory / "manual-en.html",
            )

    @patch("platform_support.documentation.os.startfile", create=True)
    def test_open_manual_uses_windows_file_association(self, startfile):
        with patch.object(documentation, "get_documentation_directory", return_value=self.directory):
            manual = documentation.open_manual("en")
        startfile.assert_called_once_with(manual)


if __name__ == "__main__":
    unittest.main()
