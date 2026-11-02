import unittest

import bot_prefs
import version


class VersionTests(unittest.TestCase):
    def test_version_is_one_place(self):
        self.assertEqual(version.VERSION, "1.3.2")
        self.assertEqual(version.APP_TITLE, "Grokbot Voice v1.3.2")


class BotPrefTests(unittest.TestCase):
    def test_new_bots_default_on_until_unchecked(self):
        prefs = bot_prefs.fresh()
        self.assertTrue(bot_prefs.allows_auto(prefs, "Larry"))
        bot_prefs.note_bots(prefs, ["Larry", "Amy"])
        self.assertTrue(bot_prefs.allows_auto(prefs, "Larry"))
        prefs["bots"]["Amy"]["read"] = False
        self.assertFalse(bot_prefs.allows_auto(prefs, "Amy"))
        self.assertTrue(bot_prefs.allows_auto(prefs, "Larry"))
        prefs["new_bots"] = False
        self.assertFalse(bot_prefs.allows_auto(prefs, "Cameron"))
        self.assertFalse(bot_prefs.allows_auto(prefs, "Larry"))
        prefs["bots"]["Larry"]["read"] = True
        self.assertTrue(bot_prefs.allows_auto(prefs, "Larry"))
        self.assertFalse(bot_prefs.allows_auto(prefs, "Amy"))

    def test_voice_falls_back_to_the_default(self):
        prefs = bot_prefs.fresh()
        bot_prefs.note_bots(prefs, ["Larry", "Amy"])
        self.assertEqual(bot_prefs.voice_choice(prefs, "Larry"), ("", None, None))
        prefs["bots"]["Amy"]["voice"] = "Jenny (natural)"
        prefs["bots"]["Amy"]["speed"] = 1.2
        prefs["bots"]["Amy"]["pitch"] = -2
        self.assertEqual(bot_prefs.voice_choice(prefs, "Amy"), ("Jenny (natural)", 1.2, -2))
        self.assertEqual(bot_prefs.voice_choice(prefs, "Larry"), ("", None, None))

    def test_toolbar_tips_name_the_real_shortcuts(self):
        self.assertIn("Ctrl+Alt+S", bot_prefs.TOOLBAR_TIPS["stop"])
        self.assertIn("stop reading and stop monitoring", bot_prefs.TOOLBAR_TIPS["stop"])
        self.assertIn("Ctrl+Alt+P", bot_prefs.TOOLBAR_TIPS["pause"])
        self.assertEqual(bot_prefs.TOOLBAR_TIPS["gear"], "Gear: Settings")
        self.assertIn("Ctrl+Alt+Q", bot_prefs.TOOLBAR_TIPS["power"])
        for name in ("back", "stop", "pause", "play", "next", "gear", "power"):
            self.assertTrue(bot_prefs.TOOLBAR_TIPS[name])
