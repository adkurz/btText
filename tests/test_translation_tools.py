import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import translations


class TranslationToolsTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.project_root = Path(self.temporary_directory.name)
        self.locale_directory = self.project_root / "locale"
        self.template_file = self.locale_directory / "bttext.pot"
        patches = (
            patch.object(translations, "PROJECT_ROOT", self.project_root),
            patch.object(
                translations,
                "MAPPING_FILE",
                self.project_root / "babel.cfg",
            ),
            patch.object(
                translations,
                "LOCALE_DIRECTORY",
                self.locale_directory,
            ),
            patch.object(translations, "TEMPLATE_FILE", self.template_file),
        )
        for path_patch in patches:
            path_patch.start()
            self.addCleanup(path_patch.stop)

    def _write_catalog_pair(
        self,
        directory_language,
        header_language,
        plural_forms,
    ):
        self.template_file.parent.mkdir(parents=True, exist_ok=True)
        self.template_file.write_text(
            'msgid ""\n'
            'msgstr ""\n'
            '"Content-Type: text/plain; charset=utf-8\\n"\n'
            "\n"
            "#: example.py:1\n"
            'msgid "Hello"\n'
            'msgstr ""\n',
            encoding="utf-8",
        )
        catalog_file = (
            self.locale_directory
            / directory_language
            / "LC_MESSAGES"
            / "bttext.po"
        )
        catalog_file.parent.mkdir(parents=True)
        catalog_file.write_text(
            'msgid ""\n'
            'msgstr ""\n'
            '"Language: {}\\n"\n'
            '"Plural-Forms: {}\\n"\n'
            '"Content-Type: text/plain; charset=utf-8\\n"\n'
            "\n"
            "#: example.py:1\n"
            'msgid "Hello"\n'
            'msgstr "Hallo"\n'.format(
                header_language,
                plural_forms,
            ),
            encoding="utf-8",
        )
        return catalog_file

    @patch("tools.translations.importlib.util.find_spec", return_value=object())
    @patch("tools.translations.subprocess.run")
    def test_extract_uses_deterministic_babel_options(self, run, find_spec):
        translations.extract()

        command = run.call_args.args[0]
        self.assertEqual(
            command[:3],
            [
                translations.sys.executable,
                "-m",
                "babel.messages.frontend",
            ],
        )
        self.assertIn("extract", command)
        self.assertIn("--add-comments", command)
        self.assertIn("Translators:", command)
        self.assertIn("--sort-by-file", command)
        self.assertNotIn("--sort-output", command)
        self.assertIn("--no-wrap", command)
        self.assertIn("--project", command)
        self.assertIn("btText", command)
        self.assertIn("--version", command)
        self.assertIn("--copyright-holder", command)
        self.assertNotIn("--omit-header", command)
        self.assertIn("pgettext:1c,2", command)
        self.assertEqual(command[-1], ".")
        run.assert_called_once()

    @patch("tools.translations.importlib.util.find_spec", return_value=None)
    def test_missing_babel_has_an_actionable_error(self, find_spec):
        with self.assertRaisesRegex(
            RuntimeError,
            "requirements-dev.txt",
        ):
            translations.extract()

    @patch("tools.translations._run_babel")
    def test_new_language_can_be_initialized_without_code_changes(self, run):
        self.template_file.parent.mkdir(parents=True)
        self.template_file.touch()

        translations.initialize_catalog("pt-BR")

        command = run.call_args.args[0]
        self.assertIn("init", command)
        self.assertIn("pt_BR", command)

    @patch("tools.translations._run_babel")
    def test_existing_catalog_is_not_overwritten(self, run):
        self.template_file.parent.mkdir(parents=True)
        self.template_file.touch()
        catalog = (
            self.locale_directory
            / "de"
            / "LC_MESSAGES"
            / "bttext.po"
        )
        catalog.parent.mkdir(parents=True)
        catalog.touch()

        with self.assertRaises(FileExistsError):
            translations.initialize_catalog("de")

        run.assert_not_called()

    def test_source_english_and_system_catalogs_are_rejected(self):
        self.template_file.parent.mkdir(parents=True)
        self.template_file.touch()

        for language in ("en", "system"):
            with self.subTest(language=language):
                with self.assertRaises(ValueError):
                    translations.initialize_catalog(language)

    def test_catalog_language_must_match_its_directory(self):
        catalog_file = self._write_catalog_pair(
            "fr",
            "de",
            "nplurals=2; plural=(n != 1);",
        )

        with self.assertRaisesRegex(
            translations.TranslationCheckError,
            "declares language 'de', expected 'fr'",
        ):
            translations._validate_catalog(
                self.template_file,
                catalog_file,
            )

    def test_catalog_plural_forms_must_match_its_language(self):
        catalog_file = self._write_catalog_pair(
            "fr",
            "fr",
            "nplurals=2; plural=(n != 1);",
        )

        with self.assertRaisesRegex(
            translations.TranslationCheckError,
            "expected 'nplurals=2; plural=\\(n > 1\\);' for fr",
        ):
            translations._validate_catalog(
                self.template_file,
                catalog_file,
            )

    @patch("tools.translations.extract")
    def test_check_rejects_an_outdated_template(self, extract):
        self.template_file.parent.mkdir(parents=True)
        self.template_file.write_text("old", encoding="utf-8")

        def write_new_template(output_file):
            output_file.write_text("new", encoding="utf-8")

        extract.side_effect = write_new_template

        with self.assertRaisesRegex(
            translations.TranslationCheckError,
            "template is out of date",
        ):
            translations.check_catalogs()

    @patch("tools.translations._validate_catalog")
    @patch("tools.translations._run_babel")
    @patch("tools.translations.extract")
    def test_check_compiles_without_requiring_a_committed_mo_file(
        self,
        extract,
        run_babel,
        validate_catalog,
    ):
        self.template_file.parent.mkdir(parents=True)
        self.template_file.write_text("template", encoding="utf-8")
        po_file = (
            self.locale_directory
            / "nl"
            / "LC_MESSAGES"
            / "bttext.po"
        )
        po_file.parent.mkdir(parents=True)
        po_file.write_text("catalog", encoding="utf-8")

        def copy_template(output_file):
            output_file.write_text("template", encoding="utf-8")

        extract.side_effect = copy_template

        translations.check_catalogs()

        run_babel.assert_called_once()
        validate_catalog.assert_called_once()


if __name__ == "__main__":
    unittest.main()
