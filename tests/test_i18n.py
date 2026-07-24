import gettext
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import i18n


class I18nTestCase(unittest.TestCase):
    def tearDown(self):
        i18n.initialize("en", Path("missing-locale-directory"))

    @staticmethod
    def _add_catalog(locale_directory, language):
        catalog = (
            Path(locale_directory)
            / language
            / "LC_MESSAGES"
            / "bttext.mo"
        )
        catalog.parent.mkdir(parents=True)
        catalog.touch()

    def test_available_languages_are_discovered_from_catalogs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            self._add_catalog(temporary_directory, "de")
            self._add_catalog(temporary_directory, "pt_BR")
            self._add_catalog(temporary_directory, "invalid language")
            self._add_catalog(temporary_directory, "nl-NL")

            languages = i18n.get_available_languages(temporary_directory)

        self.assertEqual(languages, ("en", "de", "pt_BR"))

    def test_explicit_language_is_resolved_from_available_catalogs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            self._add_catalog(temporary_directory, "de")

            self.assertEqual(
                i18n.resolve_language("de-DE", temporary_directory),
                "de",
            )
            self.assertEqual(
                i18n.resolve_language("en", temporary_directory),
                "en",
            )

    def test_language_without_catalog_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(ValueError):
                i18n.resolve_language("fr", temporary_directory)

    def test_well_formed_new_language_can_be_validated_dynamically(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            self._add_catalog(temporary_directory, "nl")

            self.assertEqual(
                i18n.validate_language("nl-NL", temporary_directory),
                "nl",
            )

    def test_malformed_language_is_rejected(self):
        for language in ("", "../de", "german", "de/../../other"):
            with self.subTest(language=language):
                with self.assertRaises(ValueError):
                    i18n.validate_language(language)

    @patch("i18n.locale.getlocale", return_value=("de_DE", "UTF-8"))
    def test_system_language_uses_supported_locale(self, getlocale):
        with tempfile.TemporaryDirectory() as temporary_directory:
            self._add_catalog(temporary_directory, "de")

            self.assertEqual(
                i18n.resolve_language("system", temporary_directory),
                "de",
            )

    @patch("i18n.locale.getlocale", return_value=(None, None))
    def test_system_language_uses_wx_locale_after_wx_app_reset(self, getlocale):
        wx_module = Mock()
        wx_module.Locale.GetSystemLanguage.return_value = 376
        wx_module.Locale.GetLanguageInfo.return_value = Mock(
            CanonicalName="de_DE",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            self._add_catalog(temporary_directory, "de")

            self.assertEqual(
                i18n.resolve_language(
                    "system",
                    temporary_directory,
                    wx_module,
                ),
                "de",
            )

        getlocale.assert_not_called()

    @patch("i18n.locale.getlocale", return_value=("fr_FR", "UTF-8"))
    def test_unsupported_system_language_falls_back_to_english(self, getlocale):
        self.assertEqual(
            i18n.resolve_language("system", "missing-locale-directory"),
            "en",
        )

    def test_source_english_does_not_require_a_catalog(self):
        active_language = i18n.initialize(
            "en",
            "missing-locale-directory",
        )

        self.assertEqual(active_language, "en")
        self.assertEqual(i18n.get_active_language(), "en")
        self.assertEqual(i18n._("Settings"), "Settings")
        self.assertEqual(i18n.ngettext("snippet", "snippets", 2), "snippets")
        self.assertEqual(i18n.pgettext("menu", "Copy"), "Copy")

    def test_damaged_catalog_falls_back_to_english_and_reports_error(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            self._add_catalog(temporary_directory, "nl")

            with self.assertRaises(i18n.LanguageError) as context:
                i18n.initialize("nl", temporary_directory)

        self.assertEqual(
            context.exception.code,
            "language_catalog_load_failed",
        )
        self.assertEqual(i18n.get_active_language(), "en")
        self.assertEqual(i18n._("Settings"), "Settings")

    @patch("i18n.gettext.translation")
    def test_catalog_is_loaded_from_requested_directory(self, translation):
        catalog = gettext.NullTranslations()
        translation.return_value = catalog
        with tempfile.TemporaryDirectory() as temporary_directory:
            locale_directory = Path(temporary_directory)
            self._add_catalog(locale_directory, "nl")

            i18n.initialize("nl", locale_directory)

        translation.assert_called_once_with(
            "bttext",
            localedir=locale_directory,
            languages=["nl"],
            fallback=True,
        )

    @patch("i18n.gettext.translation", return_value=gettext.NullTranslations())
    def test_wx_locale_is_initialized_and_retained(self, translation):
        wx_module = Mock()
        language_info = Mock(Language=37)
        wx_module.Locale.FindLanguageInfo.return_value = language_info
        wx_locale = wx_module.Locale.return_value
        with tempfile.TemporaryDirectory() as temporary_directory:
            self._add_catalog(temporary_directory, "nl")

            i18n.initialize("nl", temporary_directory, wx_module)

        wx_module.Locale.AddCatalogLookupPathPrefix.assert_called_once_with(
            temporary_directory
        )
        wx_module.Locale.FindLanguageInfo.assert_called_once_with("nl")
        wx_module.Locale.assert_called_once_with(37)
        wx_locale.AddCatalog.assert_called_once_with("bttext")
        self.assertIs(i18n._wx_locale, wx_locale)


if __name__ == "__main__":
    unittest.main()
