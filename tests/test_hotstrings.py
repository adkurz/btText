import unittest
from types import SimpleNamespace

from hotstrings import HotstringMatcher, KeyboardHook


class HotstringMatcherTestCase(unittest.TestCase):
    def setUp(self):
        self.matcher = HotstringMatcher()
        self.snippet = SimpleNamespace(hotstring="MfG")
        self.matcher.update((self.snippet,))

    def test_matches_case_insensitively_at_space(self):
        for character in "mfg":
            self.assertIsNone(self.matcher.character(character))
        self.assertIs(self.matcher.character(" "), self.snippet)

    def test_does_not_match_inside_a_word(self):
        for character in "MfGFormular":
            self.assertIsNone(self.matcher.character(character))
        self.assertIsNone(self.matcher.character(" "))

    def test_matches_at_unicode_punctuation(self):
        for character in "MfG":
            self.matcher.character(character)
        self.assertIs(self.matcher.character("…"), self.snippet)

    def test_punctuation_can_be_part_of_user_chosen_hotstring(self):
        snippet = SimpleNamespace(hotstring=";mfg")
        self.matcher.update((snippet,))
        for character in ";mfg":
            self.assertIsNone(self.matcher.character(character))
        self.assertIs(self.matcher.character(" "), snippet)

    def test_backspace_updates_buffer(self):
        for character in "MfGX":
            self.matcher.character(character)
        self.matcher.backspace()
        self.assertIs(self.matcher.character("\t"), self.snippet)

    def test_update_resets_partial_input(self):
        for character in "Mf":
            self.matcher.character(character)
        self.matcher.update((self.snippet,))
        self.assertIsNone(self.matcher.character("G"))
        self.assertIsNone(self.matcher.character("\r"))


class KeyboardHookSmokeTestCase(unittest.TestCase):
    def test_native_hook_can_be_installed_and_removed(self):
        hook = KeyboardHook(lambda snippet, key: False)
        hook.start()
        self.addCleanup(hook.stop)
        self.assertIsNotNone(hook._handle)
        hook.stop()
        self.assertIsNone(hook._handle)
