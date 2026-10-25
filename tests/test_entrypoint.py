import unittest
import tempfile
import os
import sys
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

import btText
from core.app_settings import APPEARANCE_DARK, AppSettings, SettingsStore
from core.datamodel import DataModel
from core.events import EventEmitter
from platform_support import app_paths
from ui.database_selection import DatabaseSelection


class SingleInstanceTestCase(unittest.TestCase):
    @patch("btText.app_paths.get_log_file")
    @patch("btText.configure_logging")
    @patch("btText.theme.apply_to_app")
    @patch("btText.DataModel")
    @patch("btText.i18n.initialize")
    @patch("btText.SettingsStore")
    @patch("btText.wx.MessageBox")
    @patch("btText.wx.SingleInstanceChecker")
    @patch("btText.wx.GetUserId", return_value="test-user")
    @patch("btText.wx.App")
    def test_second_instance_exits_before_opening_database(
        self,
        app_class,
        get_user_id,
        checker_class,
        message_box,
        settings_store,
        initialize_i18n,
        data_model,
        apply_theme_to_app,
        configure_logging,
        get_log_file,
    ):
        checker_class.return_value.IsAnotherRunning.return_value = True
        settings_store.return_value.load.return_value = AppSettings(
            appearance=APPEARANCE_DARK
        )
        configure_logging.return_value = Mock()

        btText.main()

        app_class.return_value.SetAppName.assert_called_once_with("btText")
        apply_theme_to_app.assert_called_once_with(
            app_class.return_value,
            APPEARANCE_DARK,
        )
        checker_class.assert_called_once_with("btText-test-user")
        message_box.assert_called_once_with(
            "btText is already running.",
            "btText",
            btText.wx.OK | btText.wx.ICON_INFORMATION,
        )
        initialize_i18n.assert_called_once()
        data_model.assert_not_called()
        app_class.return_value.MainLoop.assert_not_called()


class SettingsStartupTestCase(unittest.TestCase):
    def _run_startup(self, store, default_database):
        with (
            patch("btText.app_paths.get_log_file"),
            patch("btText.configure_logging"),
            patch("btText.app_paths.get_database_file", return_value=default_database),
            patch("btText.SettingsStore", return_value=store),
            patch.object(store, "save", wraps=store.save) as save,
            patch("btText.wx.App") as app,
            patch("btText.wx.SingleInstanceChecker") as checker,
            patch("btText.wx.MessageBox") as message_box,
            patch("btText.theme.apply_to_app"),
            patch("btText.i18n.initialize") as initialize_i18n,
            patch("btText.DataModel") as model,
            patch("btText.select_database", return_value=None) as select_database,
            patch("btText.ui.MainFrame") as frame,
        ):
            checker.return_value.IsAnotherRunning.return_value = False

            btText.main()

        return {
            "app": app.return_value,
            "model": model,
            "frame": frame,
            "select_database": select_database,
            "save": save,
            "message_box": message_box,
            "initialize_i18n": initialize_i18n,
        }

    def _assert_failed_startup(self, calls, settings_file):
        calls["model"].assert_not_called()
        calls["frame"].assert_not_called()
        calls["select_database"].assert_not_called()
        calls["save"].assert_not_called()
        calls["app"].MainLoop.assert_not_called()
        calls["initialize_i18n"].assert_called_once()
        calls["message_box"].assert_called_once()
        message, title, flags = calls["message_box"].call_args.args
        self.assertEqual(title, "Settings error")
        self.assertEqual(flags, btText.wx.OK | btText.wx.ICON_ERROR)
        self.assertIn(str(settings_file), message)

    def test_invalid_settings_abort_before_opening_or_selecting_a_database(self):
        valid_settings = (
            b"[general]\ndatabase_file = external.db\n"
            b"allow_copied_text_cloud_upload = False\nlanguage = en\n"
            b"[hotstrings]\nenabled = False\n"
            b"[hotkeys]\ntoggle_window = CTRL+ALT+T\n"
        )
        invalid_values = {
            "hotkey": valid_settings.replace(b"CTRL+ALT+T", b"INVALID"),
            "boolean": valid_settings.replace(b"enabled = False", b"enabled = invalid"),
            "language": valid_settings.replace(b"language = en", b"language = not a language"),
            "syntax": b"not an INI section\n" + valid_settings,
            "encoding": b"\xff\xfe\x00" + valid_settings,
        }
        for failure, invalid in invalid_values.items():
            for default_exists in (False, True):
                with (
                    self.subTest(failure=failure, default_exists=default_exists),
                    tempfile.TemporaryDirectory() as temporary_directory,
                ):
                    directory = Path(temporary_directory)
                    settings_file = directory / "settings.ini"
                    original = invalid
                    settings_file.write_bytes(original)
                    default_database = directory / "data.db"
                    if default_exists:
                        default_database.write_bytes(b"default database unchanged")
                    external_database = directory / "external.db"
                    external_database.write_bytes(b"external database unchanged")
                    store = SettingsStore(settings_file)

                    calls = self._run_startup(store, default_database)

                    self._assert_failed_startup(calls, settings_file)
                    self.assertEqual(settings_file.read_bytes(), original)
                    self.assertFalse(settings_file.with_suffix(".ini.tmp").exists())
                    self.assertEqual(
                        external_database.read_bytes(), b"external database unchanged"
                    )
                    if default_exists:
                        self.assertEqual(
                            default_database.read_bytes(), b"default database unchanged"
                        )
                    else:
                        self.assertFalse(default_database.exists())

    def test_unreadable_settings_abort_without_using_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            store = SettingsStore(directory / "settings.ini")
            with patch.object(Path, "open", side_effect=PermissionError("access denied")):
                calls = self._run_startup(store, directory / "data.db")

            self._assert_failed_startup(calls, store.settings_file)
            self.assertIn("access denied", calls["message_box"].call_args.args[0])

    def test_valid_settings_keep_the_configured_database_and_privacy_options(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            settings_file = directory / "settings.ini"
            original = (
                b"[general]\ndatabase_file = external.db\nlanguage = en\n"
                b"allow_copied_text_cloud_upload = False\n"
                b"[hotstrings]\nenabled = False\n"
            )
            settings_file.write_bytes(original)
            default_database = directory / "data.db"
            default_database.touch()
            store = SettingsStore(settings_file)

            calls = self._run_startup(store, default_database)

            calls["model"].assert_called_once_with(
                unittest.mock.ANY,
                str((directory / "external.db").resolve()),
                allow_create=False,
            )
            calls["frame"].assert_called_once()
            settings = calls["frame"].call_args.args[3]
            self.assertFalse(settings.allow_copied_text_cloud_upload)
            self.assertFalse(settings.hotstrings_enabled)
            calls["app"].MainLoop.assert_called_once()
            calls["model"].return_value.close.assert_called_once()
            calls["message_box"].assert_not_called()
            calls["save"].assert_not_called()
            self.assertEqual(settings_file.read_bytes(), original)

    def test_missing_settings_allow_first_start_and_database_selection(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            store = SettingsStore(directory / "settings.ini")

            calls = self._run_startup(store, directory / "data.db")

            calls["select_database"].assert_called_once_with(None, first_start=True)
            calls["message_box"].assert_not_called()
            calls["save"].assert_not_called()
            calls["frame"].assert_not_called()
            self.assertFalse(store.settings_file.exists())


class DatabaseStartupTestCase(unittest.TestCase):
    @patch("btText.wx.MessageBox")
    @patch("btText.select_database")
    @patch("btText.app_paths.get_database_file")
    def test_incomplete_columns_allow_selecting_a_valid_database(
        self, get_database_file, select_database, message_box,
    ):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            invalid_file = root / "invalid.db"
            valid_file = root / "valid.db"
            with closing(sqlite3.connect(invalid_file)) as connection:
                connection.executescript(
                    "CREATE TABLE category (id INTEGER PRIMARY KEY, parent_id INTEGER, name TEXT);"
                    "CREATE TABLE snippet (id INTEGER PRIMARY KEY);"
                    f"PRAGMA user_version = {DataModel.SCHEMA_VERSION};"
                )
            valid_model = DataModel(EventEmitter(), valid_file)
            valid_model.close()
            original_bytes = invalid_file.read_bytes()
            get_database_file.return_value = root / "unused.db"
            select_database.return_value = DatabaseSelection(valid_file, False)
            settings = AppSettings(database_file=str(invalid_file))
            store = Mock()

            model, updated = btText._open_database(EventEmitter(), store, settings)
            try:
                self.assertIsNotNone(model)
                self.assertEqual(model.get_all_category_summaries(), ())
                self.assertEqual(model.get_hotstring_snippets(), ())
                self.assertEqual(updated.database_file, str(valid_file.resolve()))
                select_database.assert_called_once_with(None, first_start=True)
                message_box.assert_called_once()
                self.assertIn("snippet.category_id", message_box.call_args.args[0])
                store.save.assert_called_once_with(updated)
                self.assertEqual(invalid_file.read_bytes(), original_bytes)
            finally:
                if model is not None:
                    model.close()

    @patch("btText.DataModel")
    @patch("btText.app_paths.get_database_file")
    def test_legacy_database_is_adopted(
        self,
        get_database_file,
        data_model,
    ):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "data.db"
            database_file.touch()
            get_database_file.return_value = database_file
            store = Mock()
            settings = AppSettings()

            model, updated = btText._open_database(Mock(), store, settings)

            self.assertIs(model, data_model.return_value)
            data_model.assert_called_once_with(
                unittest.mock.ANY,
                database_file,
                allow_create=False,
            )
            self.assertEqual(updated.database_file, str(database_file.resolve()))
            store.save.assert_called_once_with(updated)

    @patch("btText.DataModel")
    def test_installed_default_database_is_adopted_and_persisted(
        self,
        data_model,
    ):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            bundle = root / "_internal"
            bundle.mkdir()
            (bundle / app_paths.INSTALL_MODE_MARKER).touch()
            appdata = root / "AppData" / "Roaming"
            database_file = appdata / "btText" / "data.db"
            database_file.parent.mkdir(parents=True)
            database_file.touch()
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", str(bundle), create=True),
                patch.dict(os.environ, {"APPDATA": str(appdata)}),
            ):
                store = SettingsStore(app_paths.get_settings_file())

                model, updated = btText._open_database(
                    Mock(),
                    store,
                    AppSettings(),
                )

                self.assertIs(model, data_model.return_value)
                data_model.assert_called_once_with(
                    unittest.mock.ANY,
                    database_file,
                    allow_create=False,
                )
                self.assertEqual(
                    updated.database_file,
                    str(database_file.resolve()),
                )
                self.assertIn(
                    "database_file = data.db",
                    store.settings_file.read_text(encoding="utf-8"),
                )

    @patch("btText.select_database")
    @patch("btText.DataModel")
    def test_installed_first_start_keeps_selected_portable_database_external(
        self,
        data_model,
        select_database,
    ):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            installed_bundle = root / "installed" / "_internal"
            installed_bundle.mkdir(parents=True)
            (installed_bundle / app_paths.INSTALL_MODE_MARKER).touch()
            portable_database = root / "portable" / "data.db"
            portable_database.parent.mkdir()
            portable_database.touch()
            appdata = root / "AppData" / "Roaming"
            select_database.return_value = DatabaseSelection(
                portable_database,
                False,
            )
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(
                    sys,
                    "executable",
                    str(root / "installed" / "btText.exe"),
                ),
                patch.object(
                    sys,
                    "_MEIPASS",
                    str(installed_bundle),
                    create=True,
                ),
                patch.dict(os.environ, {"APPDATA": str(appdata)}),
            ):
                store = SettingsStore(app_paths.get_settings_file())

                model, updated = btText._open_database(
                    Mock(),
                    store,
                    AppSettings(),
                )

                self.assertIs(model, data_model.return_value)
                select_database.assert_called_once_with(
                    None,
                    first_start=True,
                )
                data_model.assert_called_once_with(
                    unittest.mock.ANY,
                    portable_database,
                    allow_create=False,
                )
                self.assertEqual(
                    updated.database_file,
                    str(portable_database.resolve()),
                )
                self.assertIn(
                    f"database_file = {portable_database.resolve()}",
                    store.settings_file.read_text(encoding="utf-8"),
                )

    @patch("btText.select_database", return_value=None)
    @patch("btText.app_paths.get_database_file")
    def test_first_start_can_be_cancelled(
        self,
        get_database_file,
        select_database,
    ):
        get_database_file.return_value.exists.return_value = False
        settings = AppSettings()

        model, updated = btText._open_database(Mock(), Mock(), settings)

        self.assertIsNone(model)
        self.assertIs(updated, settings)
        select_database.assert_called_once_with(None, first_start=True)


if __name__ == "__main__":
    unittest.main()
