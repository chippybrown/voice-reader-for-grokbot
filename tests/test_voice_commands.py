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
        self.assertEqual(wake_cmd.phrase_action("Moya mute"), "mute")
        self.assertEqual(wake_cmd.phrase_action("  moya   sleep "), "mute")
        self.assertEqual(wake_cmd.phrase_action("moya wake"), "unmute")
        self.assertEqual(wake_cmd.phrase_action("moya wake up"), "unmute")
        self.assertEqual(wake_cmd.phrase_action("moya listen"), "unmute")
        self.assertEqual(wake_cmd.phrase_action("moya un mute"), "unmute")
        self.assertIsNone(wake_cmd.phrase_action("moya unmute"))
        self.assertNotIn("unmute", wake_cmd.GRAMMAR)
        self.assertIsNone(wake_cmd.phrase_action(""))
        self.assertIsNone(wake_cmd.phrase_action("[unk]"))
        self.assertIsNone(wake_cmd.phrase_action("moya please mute"))

    def test_echo_is_ignored_and_resets(self):
        action, quiet, reset = wake_cmd.consider_phrase("moya mute", True, 10.0, 0.0)
        self.assertIsNone(action)
        self.assertTrue(reset)
        action, quiet, reset = wake_cmd.consider_phrase("moya wake", False, 10.0, 10.5)
        self.assertIsNone(action)
        action, quiet, reset = wake_cmd.consider_phrase("moya wake", False, 11.0, 10.5)
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
