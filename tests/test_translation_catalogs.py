import gettext
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_FILE = PROJECT_ROOT / "locale" / "bttext.pot"
GERMAN_CATALOG = (
    PROJECT_ROOT
    / "locale"
    / "de"
    / "LC_MESSAGES"
    / "bttext.po"
)
GERMAN_COMPILED_CATALOG = GERMAN_CATALOG.with_suffix(".mo")


class TranslationCatalogsTestCase(unittest.TestCase):
    @staticmethod
    def _message_blocks(catalog):
        return tuple(
            block
            for block in catalog.replace("\r\n", "\n").split("\n\n")
            if "\n#:" in "\n" + block
            and "\nmsgid " in "\n" + block
        )

    def test_template_contains_project_metadata_and_translator_guidance(self):
        template = TEMPLATE_FILE.read_text(encoding="utf-8")

        self.assertIn("Project-Id-Version: btText 1.0", template)
        self.assertIn("#. Translators:", template)
        self.assertIn('msgctxt "snippet weight"', template)
        self.assertIn("msgid_plural", template)
        self.assertNotIn("C:/Users/", template)
        self.assertNotIn(
            '#. Translators: "&" marks the keyboard mnemonic.',
            template,
        )
        self.assertNotIn(
            '#. Translators: Keep the shortcut after "\\t".',
            template,
        )
        self.assertIn(
            "#. Translators: Settings-dialog button that saves and activates "
            "pending",
            template,
        )
        self.assertIn(
            "#. changes without closing the dialog. "
            '"&" marks the keyboard mnemonic.',
            template,
        )
        for block in self._message_blocks(template):
            with self.subTest(block=block):
                self.assertIn("#. Translators:", block)

        category_heading = template.index('msgid "&Categories"')
        snippet_heading = template.index('msgid "&Snippets"')
        search_command = template.index('msgid "&Search...\\tF3"')
        self.assertLess(category_heading, snippet_heading)
        self.assertLess(snippet_heading, search_command)

    def test_german_catalog_has_locale_metadata_and_relative_locations(self):
        catalog = GERMAN_CATALOG.read_text(encoding="utf-8")

        self.assertIn('"Language: de\\n"', catalog)
        self.assertIn(
            '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"',
            catalog,
        )
        self.assertIn("#. Translators:", catalog)
        self.assertIn("#: ui/", catalog)
        self.assertNotIn("C:/Users/", catalog)

    def test_german_catalog_is_complete_and_uses_project_terminology(self):
        with GERMAN_COMPILED_CATALOG.open("rb") as catalog_file:
            translation = gettext.GNUTranslations(catalog_file)

        self.assertEqual(translation.gettext("&Snippets"), "&Textbausteine")
        self.assertEqual(translation.gettext("&Apply"), "Ü&bernehmen")
        self.assertEqual(
            translation.ngettext(
                "Deleted {count} snippet.",
                "Deleted {count} snippets.",
                2,
            ),
            "{count} Textbausteine gelöscht.",
        )
        translated_messages = tuple(
            message
            for message_id, message in translation._catalog.items()
            if message_id
        )
        self.assertTrue(translated_messages)
        self.assertTrue(all(translated_messages))

    def test_german_mnemonics_are_unique_within_each_ui_group(self):
        with GERMAN_COMPILED_CATALOG.open("rb") as catalog_file:
            translation = gettext.GNUTranslations(catalog_file)

        groups = (
            (
                "&Categories",
                "&Snippets",
                "&Search...\tF3",
                "&Settings...\tCtrl+,",
                "&Edit",
                "&Help",
            ),
            ("&Search", "Search &results", "&Show snippet", "&Cancel"),
            (
                "&General",
                "&Keyboard",
                "&Language",
                "&OK",
                "&Cancel",
                "&Apply",
                "Current &hotkey",
                "&Record new shortcut",
                "Cancel &recording",
                "Use &default",
            ),
            ("&Name", "&Category", "&Weight", "C&ontent", "&Save", "&Cancel"),
        )
        for group in groups:
            with self.subTest(group=group):
                labels = tuple(translation.gettext(message) for message in group)
                mnemonics = tuple(
                    label.split("&", 1)[1][0].casefold()
                    for label in labels
                )
                self.assertEqual(len(mnemonics), len(set(mnemonics)))


if __name__ == "__main__":
    unittest.main()
