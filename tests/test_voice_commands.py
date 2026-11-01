import unittest

import wake_cmd


class WakeTests(unittest.TestCase):
    def test_only_speak_and_quiet(self):
        self.assertEqual(wake_cmd.phrase_action("Larry speak", "Larry"), "speak")
        self.assertEqual(wake_cmd.phrase_action("  larry   quiet ", "Larry"), "quiet")
        self.assertEqual(sorted(wake_cmd.phrases_for("Larry")), ["larry quiet", "larry speak"])
        grammar = wake_cmd.grammar_for("Larry")
        self.assertIn('"larry speak"', grammar)
        self.assertIn('"larry quiet"', grammar)
        self.assertIn('"[unk]"', grammar)
        self.assertIsNone(wake_cmd.phrase_action("", "Larry"))
        self.assertIsNone(wake_cmd.phrase_action("[unk]", "Larry"))
        self.assertIsNone(wake_cmd.phrase_action("larry please speak", "Larry"))

    def test_last_phrase_wins_and_unk_is_ignored(self):
        self.assertEqual(wake_cmd.phrase_action("[unk] larry speak larry speak", "Larry"), "speak")
        self.assertEqual(wake_cmd.phrase_action("[unk] larry quiet [unk]", "Larry"), "quiet")
        self.assertEqual(wake_cmd.phrase_action("larry speak larry quiet", "Larry"), "quiet")
        self.assertEqual(wake_cmd.phrase_action("larry quiet larry speak", "Larry"), "speak")
        self.assertEqual(wake_cmd.phrase_action("larry speak quiet", "Larry"), "speak")
        self.assertIsNone(wake_cmd.phrase_action("[unk]", "Larry"))

    def test_custom_name_and_fuzzy_match(self):
        self.assertEqual(wake_cmd.phrase_action("design bot quiet", "Design Bot"), "quiet")
        self.assertEqual(wake_cmd.phrase_action("lari speak", "Larry"), "speak")
        self.assertIsNone(wake_cmd.phrase_action("moya quiet", "Larry"))
        self.assertEqual(wake_cmd.resolve_wake_name("Larry", "Someone", "Amy", "Bob"), "Larry")
        self.assertEqual(wake_cmd.resolve_wake_name("", "Someone", "Amy", "Bob"), "Someone")
        self.assertEqual(wake_cmd.resolve_wake_name("", "", "Amy", "Bob"), "Amy")
        self.assertEqual(wake_cmd.resolve_wake_name("", "", "", "Bob"), "Bob")
        warning = "WARNING Ignoring word missing in vocabulary: 'xyzzy'"
        self.assertEqual(wake_cmd.name_words_missing(warning, "Xyzzy Bot"), ["xyzzy"])

    def test_quiet_works_while_speaking_and_speak_does_not(self):
        action, _quiet, reset = wake_cmd.consider_phrase("larry quiet", True, 10.0, 0.0, "Larry")
        self.assertEqual(action, "quiet")
        self.assertTrue(reset)
        action, _quiet, reset = wake_cmd.consider_phrase("larry speak", True, 10.0, 0.0, "Larry")
        self.assertIsNone(action)
        self.assertTrue(reset)
        action, _quiet, reset = wake_cmd.consider_phrase("lari quiet", True, 10.0, 0.0, "Larry")
        self.assertIsNone(action)
        self.assertTrue(reset)
        action, _quiet, reset = wake_cmd.consider_phrase("larry speak larry quiet", True, 10.0, 0.0, "Larry")
        self.assertEqual(action, "quiet")
        action, _quiet, reset = wake_cmd.consider_phrase("larry quiet larry speak", True, 10.0, 0.0, "Larry")
        self.assertIsNone(action)
        action, quiet, reset = wake_cmd.consider_phrase("larry speak", False, 10.0, 10.5, "Larry")
        self.assertIsNone(action)
        action, quiet, reset = wake_cmd.consider_phrase("larry speak", False, 11.0, 10.5, "Larry")
        self.assertEqual(action, "speak")
        self.assertGreater(quiet, 11.0)
        self.assertFalse(reset)


if __name__ == "__main__":
    unittest.main()
