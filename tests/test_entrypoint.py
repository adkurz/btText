import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import btText
from core.app_settings import AppSettings


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
