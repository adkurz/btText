import unittest
from unittest.mock import Mock, patch

import wx

from ui import hotkey_recorder


def key_event(
    *,
    key_code: int,
    raw_key_code: int = 0,
    unicode_key: int = wx.WXK_NONE,
    control: bool = False,
    shift: bool = False,
    alt: bool = False,
) -> Mock:
    """Create the wx key-event surface used by the recorder decoder."""
    event = Mock()
    event.GetKeyCode.return_value = key_code
    event.GetRawKeyCode.return_value = raw_key_code
    event.GetUnicodeKey.return_value = unicode_key
    event.ControlDown.return_value = control
    event.ShiftDown.return_value = shift
    event.AltDown.return_value = alt
    event.MetaDown.return_value = False
    event.GetModifiers.return_value = 0
    return event


class HotkeyRecorderTestCase(unittest.TestCase):
    def test_raw_modifier_key_is_ignored(self):
        event = key_event(key_code=0, raw_key_code=0xA5)

        self.assertTrue(hotkey_recorder.is_modifier_event(event))

    def test_ctrl_control_code_is_normalized_to_letter(self):
        event = key_event(key_code=1, control=True)

        self.assertEqual(hotkey_recorder.key_name_from_event(event), "A")

    def test_raw_oem_virtual_key_is_preserved(self):
        event = key_event(key_code=0, raw_key_code=0xBA, control=True)

        self.assertEqual(
            hotkey_recorder.key_name_from_event(event),
            "VK_BA",
        )

    def test_unicode_key_is_used_when_wx_key_code_is_unknown(self):
        event = key_event(key_code=0, unicode_key=ord("Z"))

        self.assertEqual(hotkey_recorder.key_name_from_event(event), "Z")

    def test_function_key_is_normalized(self):
        event = key_event(key_code=wx.WXK_F12)

        self.assertEqual(hotkey_recorder.key_name_from_event(event), "F12")

    @patch("ui.hotkey_recorder.windows_modifier_down", return_value=True)
    def test_event_is_converted_to_validated_hotkey(self, windows_down):
        event = key_event(
            key_code=ord("T"),
            raw_key_code=ord("T"),
            control=True,
            shift=True,
            alt=True,
        )

        hotkey = hotkey_recorder.hotkey_from_event(event)

        self.assertEqual(str(hotkey), "CTRL+SHIFT+ALT+WIN+T")

    def test_unsupported_key_is_rejected(self):
        event = key_event(key_code=0)

        with self.assertRaisesRegex(
            ValueError,
            "The pressed key is not supported",
        ):
            hotkey_recorder.hotkey_from_event(event)

    @patch("ui.hotkey_recorder.is_windows_key_down")
    def test_wx_meta_modifier_avoids_native_fallback(self, native_state):
        event = key_event(key_code=ord("T"))
        event.MetaDown.return_value = True

        self.assertTrue(hotkey_recorder.windows_modifier_down(event))

        native_state.assert_not_called()

    @patch("ui.hotkey_recorder.wx.GetKeyState", return_value=False)
    @patch(
        "ui.hotkey_recorder.is_windows_key_down",
        return_value=True,
    )
    def test_native_windows_key_state_is_used_as_fallback(
        self,
        native_state,
        get_key_state,
    ):
        event = key_event(key_code=ord("T"))

        self.assertTrue(hotkey_recorder.windows_modifier_down(event))

        native_state.assert_called_once_with()
