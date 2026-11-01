import unittest

import wake_cmd

PACTL = """
Source Output #41
	Driver: protocol-native.c
	Properties:
		application.name = "Firefox"
		application.process.binary = "firefox"

Source Output #42
	Properties:
		application.name = "Grok Bot"
		application.process.binary = "grok-bot"

Source Output #7
	Properties:
		application.name = "Grokbot Voice"
		application.process.binary = "grokbot-voice"
"""


class WakeTests(unittest.TestCase):
    def test_only_the_known_phrases(self):
        self.assertEqual(wake_cmd.phrase_action("Larry mute", "Larry"), "mute")
        self.assertEqual(wake_cmd.phrase_action("  larry   sleep ", "Larry"), "mute")
        self.assertEqual(wake_cmd.phrase_action("larry wake", "Larry"), "unmute")
        self.assertEqual(wake_cmd.phrase_action("larry wake up", "Larry"), "unmute")
        self.assertEqual(wake_cmd.phrase_action("larry listen", "Larry"), "unmute")
        self.assertEqual(wake_cmd.phrase_action("larry un mute", "Larry"), "unmute")
        self.assertIsNone(wake_cmd.phrase_action("larry unmute", "Larry"))
        self.assertNotIn("unmute", wake_cmd.grammar_for("Larry"))
        self.assertIsNone(wake_cmd.phrase_action("", "Larry"))
        self.assertIsNone(wake_cmd.phrase_action("[unk]", "Larry"))
        self.assertIsNone(wake_cmd.phrase_action("larry please mute", "Larry"))

    def test_noisy_mic_results(self):
        self.assertEqual(wake_cmd.phrase_action("[unk] larry mute larry mute", "Larry"), "mute")
        self.assertEqual(wake_cmd.phrase_action("larry mute larry mute larry mute", "Larry"), "mute")
        self.assertEqual(wake_cmd.phrase_action("[unk] sleep larry mute [unk]", "Larry"), "mute")
        self.assertEqual(wake_cmd.phrase_action("larry mute larry wake", "Larry"), "unmute")
        self.assertEqual(wake_cmd.phrase_action("larry wake up larry mute", "Larry"), "mute")
        self.assertEqual(wake_cmd.phrase_action("[unk]", "Larry"), None)

    def test_custom_name_and_fuzzy_match(self):
        self.assertEqual(wake_cmd.phrase_action("[unk] larry mute [unk]", "Larry"), "mute")
        self.assertEqual(wake_cmd.phrase_action("lari mute", "Larry"), "mute")
        self.assertEqual(wake_cmd.phrase_action("larry mute larry wake", "Larry"), "unmute")
        self.assertIsNone(wake_cmd.phrase_action("moya mute", "Larry"))
        self.assertEqual(wake_cmd.resolve_wake_name("Larry", "Someone", "Amy", "Bob"), "Larry")
        self.assertEqual(wake_cmd.resolve_wake_name("", "Someone", "Amy", "Bob"), "Someone")
        self.assertEqual(wake_cmd.resolve_wake_name("", "", "Amy", "Bob"), "Amy")
        self.assertEqual(wake_cmd.resolve_wake_name("", "", "", "Bob"), "Bob")
        warning = "WARNING Ignoring word missing in vocabulary: 'xyzzy'"
        self.assertEqual(wake_cmd.name_words_missing(warning, "Xyzzy Bot"), ["xyzzy"])

    def test_echo_is_ignored_and_resets(self):
        action, quiet, reset = wake_cmd.consider_phrase("larry mute", True, 10.0, 0.0, "Larry")
        self.assertIsNone(action)
        self.assertTrue(reset)
        action, quiet, reset = wake_cmd.consider_phrase("larry wake", False, 10.0, 10.5, "Larry")
        self.assertIsNone(action)
        action, quiet, reset = wake_cmd.consider_phrase("larry wake", False, 11.0, 10.5, "Larry")
        self.assertEqual(action, "unmute")
        self.assertGreater(quiet, 11.0)
        self.assertFalse(reset)

    def test_pactl_matches_grok_bot_only(self):
        self.assertEqual(wake_cmd.grok_bot_source_ids(PACTL), ["42"])

    def test_names(self):
        self.assertTrue(wake_cmd.is_grok_bot_name("Grok Bot"))
        self.assertTrue(wake_cmd.is_grok_bot_name(r"C:\Program Files\Grok Bot\Grok Bot.exe"))
        self.assertTrue(wake_cmd.is_grok_bot_name("sand"))
        self.assertFalse(wake_cmd.is_grok_bot_name("Grokbot Voice"))
        self.assertFalse(wake_cmd.is_grok_bot_name("grokbot-voice"))
        self.assertFalse(wake_cmd.is_grok_bot_name("firefox"))

    def test_windows_consent_name(self):
        self.assertEqual(
            wake_cmd.consent_key_name(r"C:\Users\Chip\AppData\Local\Programs\Grok Bot\Grok Bot.exe"),
            "C:#Users#Chip#AppData#Local#Programs#Grok Bot#Grok Bot.exe",
        )


if __name__ == "__main__":
    unittest.main()
