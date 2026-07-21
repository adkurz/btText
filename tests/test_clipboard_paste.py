import unittest

from clipboard_paste import PendingPaste


class RecordingClipboardSnapshot:
    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class PendingPasteTestCase(unittest.TestCase):
    def test_discard_snapshot_releases_saved_clipboard_data(self):
        snapshot = RecordingClipboardSnapshot()
        pending = PendingPaste(snapshot, b"marker")

        pending.discard_snapshot()

        self.assertEqual(snapshot.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
