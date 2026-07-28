import unittest
from unittest.mock import Mock, patch

import btText
from app_settings import AppSettings


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


if __name__ == "__main__":
    unittest.main()
