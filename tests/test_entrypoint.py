import unittest
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import btText
from core.app_settings import AppSettings, SettingsStore
from platform_support import app_paths


class SingleInstanceTestCase(unittest.TestCase):
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
    ):
        checker_class.return_value.IsAnotherRunning.return_value = True
        settings_store.return_value.load.return_value = AppSettings()

        btText.main()

        app_class.return_value.SetAppName.assert_called_once_with("btText")
        checker_class.assert_called_once_with("btText-test-user")
        message_box.assert_called_once_with(
            "btText is already running.",
            "btText",
            btText.wx.OK | btText.wx.ICON_INFORMATION,
        )
        initialize_i18n.assert_called_once()
        data_model.assert_not_called()
        app_class.return_value.MainLoop.assert_not_called()


class DatabaseStartupTestCase(unittest.TestCase):
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
