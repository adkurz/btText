import unittest

from core.hotstrings import HotstringMatcher


class HotstringMatcherTestCase(unittest.TestCase):
    def setUp(self):
        self.matcher = HotstringMatcher[str]()
        self.payload = "payload"
        self.matcher.update({"MfG": self.payload})

    def test_matches_with_exact_case_at_space(self):
        for character in "MfG":
            self.assertIsNone(self.matcher.character(character))
        self.assertEqual(self.matcher.character(" "), self.payload)

    def test_does_not_match_with_different_case(self):
        for value in ("mfg", "MFG"):
            with self.subTest(value=value):
                self.matcher.reset()
                for character in value:
                    self.assertIsNone(self.matcher.character(character))
                self.assertIsNone(self.matcher.character(" "))

    def test_does_not_match_inside_a_word(self):
        for character in "MfGFormular":
            self.assertIsNone(self.matcher.character(character))
        self.assertIsNone(self.matcher.character(" "))

    def test_matches_at_unicode_punctuation(self):
        for character in "MfG":
            self.matcher.character(character)
        self.assertEqual(
            self.matcher.character("\N{HORIZONTAL ELLIPSIS}"),
            self.payload,
        )

    def test_punctuation_can_be_part_of_user_chosen_hotstring(self):
        self.matcher.update({";mfg": self.payload})
        for character in ";mfg":
            self.assertIsNone(self.matcher.character(character))
        self.assertEqual(self.matcher.character(" "), self.payload)

    def test_backspace_updates_buffer(self):
        for character in "MfGX":
            self.matcher.character(character)
        self.matcher.backspace()
        self.assertEqual(self.matcher.character("\t"), self.payload)

    def test_update_resets_partial_input(self):
        for character in "Mf":
            self.matcher.character(character)
        self.matcher.update({"MfG": self.payload})
        self.assertIsNone(self.matcher.character("G"))
        self.assertIsNone(self.matcher.character("\r"))

    def test_update_ignores_empty_trigger(self):
        self.matcher.update({"": self.payload})
        self.assertIsNone(self.matcher.character(" "))
