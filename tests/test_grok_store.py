# The chat-file reader is what Linux uses instead of Windows UI Automation.
import os
import shutil
import stat
import tempfile
import unittest

import grok_store
import platform_linux
import wake_cmd


def _blob(directory, key, payload):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, grok_store.encode_base32(key) + ".blob")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(payload)
    return path


class StoreTests(unittest.TestCase):
    def test_base32_roundtrip(self):
        key = "sand.client.slice.account.grok|user_1.transcript.replicas.agent-123"
        self.assertEqual(grok_store.decode_base32(grok_store.encode_base32(key)), key)
        self.assertIsNone(grok_store.decode_base32("not slice data!!!"))

    def test_replies_skip_the_user_and_widgets(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"agent-123","name":"Moya"}]}}')
            _blob(store, "sand.client.slice.account.a.transcript.replicas.agent-123",
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"message","role":"user","seq":1,"timestampMs":1700000000000,"content":"please look at this"},'
                  '{"kind":"send-message","seq":2,"timestampMs":1700000001000,"message":{"type":"text","content":"Here is the answer."}},'
                  '{"kind":"send-message","seq":3,"timestampMs":1700000001500,"message":{"type":"widget","content":"do not read this button"}},'
                  '{"kind":"message","role":"assistant","seq":4,"timestampMs":1700000002000,"content":"And another line."}'
                  ']}}')
            lines, names = grok_store.reply_lines(store)
            self.assertIn("Moya", names)
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[0].startswith("Moya "))
            self.assertIn("#2 ", lines[0])
            self.assertIn("Here is the answer.", lines[0])
            self.assertIn("And another line.", lines[1])
            self.assertNotIn("please look", " ".join(lines))
            self.assertNotIn("do not read", " ".join(lines))
        finally:
            shutil.rmtree(root)

    def test_outbound_agent_notes_are_not_replies(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.transcript.replicas.agent-123",
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"message","role":"assistant","id":"agent-outbound-9","toAgent":{"id":"cloud"},"seq":1,"timestampMs":1700000000000,"content":"ask the other agent"},'
                  '{"kind":"message","role":"assistant","id":"note-1","seq":2,"timestampMs":1700000001000,"content":"a private aside"},'
                  '{"kind":"send-message","id":"reply-1","seq":3,"timestampMs":1700000002000,"message":{"type":"text","content":"Here is what I found."}}'
                  ']}}')
            lines, _names = grok_store.reply_lines(store)
            spoken = " ".join(lines)
            self.assertIn("Here is what I found.", spoken)
            self.assertIn("a private aside", spoken)
            self.assertNotIn("ask the other agent", spoken)
        finally:
            shutil.rmtree(root)

    def test_rewrite_does_not_reread_old_replies(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            key = "sand.client.slice.account.a.transcript.replicas.agent-123"
            _blob(store, key,
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"send-message","id":"m1","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"first"}},'
                  '{"kind":"send-message","id":"m2","seq":2,"timestampMs":1700000001000,"message":{"type":"text","content":"second"}}'
                  ']}}')
            lines, _names, keylists, active = grok_store.reply_snapshot(store)
            seen = set()
            grok_store.mark_seen(seen, keylists)
            self.assertEqual(grok_store.unseen_lines(seen, lines, keylists), [])
            # Compact the slice: drop the first reply, renumber seq, add a new one.
            _blob(store, key,
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"send-message","id":"m2","seq":9,"timestampMs":1700000001000,"message":{"type":"text","content":"second"}},'
                  '{"kind":"send-message","id":"m3","seq":10,"timestampMs":1700000002000,"message":{"type":"text","content":"third"}}'
                  ']}}')
            lines, _names, keylists, active2 = grok_store.reply_snapshot(store)
            self.assertEqual(active, active2)
            self.assertEqual(grok_store.unseen_lines(seen, lines, keylists), [
                line for line in lines if "third" in line
            ])
            lines, _names, keylists, _active = grok_store.reply_snapshot(store)
            self.assertEqual(grok_store.unseen_lines(seen, lines, keylists), [])
        finally:
            shutil.rmtree(root)

    def test_active_chat_is_the_newest_file(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            older = _blob(store, "sand.client.slice.account.a.transcript.replicas.old-bot",
                          '{"schemaVersion":1,"value":{"entries":[{"kind":"send-message","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"old chat"}}]}}')
            newer = _blob(store, "sand.client.slice.account.a.transcript.replicas.new-bot",
                          '{"schemaVersion":1,"value":{"entries":[{"kind":"send-message","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"new chat"}}]}}')
            os.utime(older, (1_700_000_000, 1_700_000_000))
            os.utime(newer, (1_700_000_100, 1_700_000_100))
            lines, _names = grok_store.reply_lines(store)
            self.assertEqual(len(lines), 1)
            self.assertIn("new chat", lines[0])
        finally:
            shutil.rmtree(root)

    def test_wake_name_comes_from_the_roster_then_the_open_chat(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"a","name":"Larry","primary":true},{"id":"b","name":"Amy"}]}}')
            _blob(store, "sand.client.slice.account.a.transcript.replicas.b",
                  '{"schemaVersion":1,"value":{"entries":[{"kind":"send-message","id":"m","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"hi"}}]}}')
            self.assertEqual(grok_store.primary_bot_name(store), "Larry")
            self.assertEqual(grok_store.active_bot_name(store), "Amy")
            self.assertEqual(wake_cmd.resolve_wake_name("", "", grok_store.primary_bot_name(store), grok_store.active_bot_name(store)), "Larry")
        finally:
            shutil.rmtree(root)

    def test_chief_voice_regex_still_matches(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            os.makedirs(store)
            with open(os.path.join(store, "settings.blob"), "w", encoding="utf-8") as handle:
                handle.write('{"id":"12345678-1234-1234-1234-123456789abc","name":"Moya","voiceId":"eve","voiceSpeed":1.1}')
            voice, speed = grok_store.chief_voice(store, "Moya")
            self.assertEqual(voice, "eve")
            self.assertAlmostEqual(speed, 1.1)
            self.assertEqual(grok_store.chief_voice(None, "Moya"), ("carina", 1.0))
        finally:
            shutil.rmtree(root)

    def test_flatpak_and_configured_folder(self):
        home = tempfile.mkdtemp()
        try:
            flatpak = os.path.join(home, ".var", "app", "com.anysphere.sand", "config", "Grok Bot", "sand-client-persistence")
            os.makedirs(flatpak)
            with open(os.path.join(flatpak, "note.blob"), "w", encoding="utf-8") as handle:
                handle.write("{}")
            found = grok_store.linux_store(os.path.join(home, ".config", "grokbot-voice"), home=home, config_home=os.path.join(home, ".config"), env={})
            self.assertEqual(found, flatpak)
            custom = os.path.join(home, "custom-chats")
            os.makedirs(custom)
            env = {"GROKBOT_CHAT_DIR": custom}
            chosen = grok_store.linux_store(os.path.join(home, ".config", "grokbot-voice"), home=home, config_home=os.path.join(home, ".config"), env=env)
            self.assertEqual(chosen, custom)
            names = [os.path.normpath(path) for path in grok_store.candidate_dirs(home, os.path.join(home, ".config"))]
            self.assertIn(os.path.normpath(os.path.join(home, ".config", "Grok Bot", "sand-client-persistence")), names)
            self.assertIn(os.path.normpath(os.path.join(home, ".config", "grok-bot", "sand-client-persistence")), names)
            self.assertIn(os.path.normpath(os.path.join(home, ".config", "Grokbot", "sand-client-persistence")), names)
            self.assertTrue(any("/snap/" in path or path.endswith("sand-client-persistence") for path in names))
        finally:
            shutil.rmtree(home)

    def test_snap_path_is_a_candidate(self):
        home = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(home, "snap", "grok-bot", "current"))
            names = grok_store.candidate_dirs(home, os.path.join(home, ".config"))
            self.assertTrue(any(os.path.join("snap", "grok-bot", "current") in path for path in names))
            self.assertTrue(any(os.path.join("snap", "grok-bot", "common") in path for path in names))
        finally:
            shutil.rmtree(home)

    def test_piper_help_check_and_player_order(self):
        root = tempfile.mkdtemp()
        try:
            binary = os.path.join(root, "piper")
            with open(binary, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\necho --output_file --length_scale\n")
            os.chmod(binary, os.stat(binary).st_mode | stat.S_IEXEC)
            self.assertTrue(platform_linux._is_tts_piper(binary))
            with open(binary, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\necho gamepad mapper\n")
            self.assertFalse(platform_linux._is_tts_piper(binary))
        finally:
            shutil.rmtree(root)
        original = platform_linux._player_bin
        real_which = platform_linux.shutil.which
        try:
            platform_linux._player_bin = None
            platform_linux.shutil.which = lambda name: "/usr/bin/" + name if name == "pw-play" else None
            self.assertEqual(platform_linux._player_command("out.wav"), ["/usr/bin/pw-play", "out.wav"])
            platform_linux._player_bin = None
            platform_linux.shutil.which = lambda name: "/usr/bin/" + name if name == "paplay" else None
            self.assertEqual(platform_linux._player_command("out.wav")[0], "/usr/bin/paplay")
        finally:
            platform_linux._player_bin = original
            platform_linux.shutil.which = real_which


if __name__ == "__main__":
    unittest.main()
