import unittest
from unittest.mock import Mock

from core.events import EventEmitter


class EventEmitterTestCase(unittest.TestCase):
    def test_listener_failure_is_logged_and_does_not_stop_later_listener(self):
        events = EventEmitter()
        failing_listener = Mock(side_effect=RuntimeError("listener failed"))
        later_listener = Mock()
        events.on("changed", failing_listener)
        events.on("changed", later_listener)

        with self.assertLogs("bttext.events", level="ERROR") as logged:
            events.emit("changed", 42)

        failing_listener.assert_called_once_with(42)
        later_listener.assert_called_once_with(42)
        self.assertIn("listener failed", logged.output[0])

    def test_listener_can_be_removed(self):
        events = EventEmitter()
        listener = Mock()
        events.on("changed", listener)

        self.assertIs(events.off("changed", listener), listener)
        events.emit("changed", 42)

        listener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
