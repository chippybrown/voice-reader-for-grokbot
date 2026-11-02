# The chat-file reader is what Linux uses instead of Windows UI Automation.
import json
import os
import shutil
import stat
import tempfile
import unittest

import grok_store
import platform_linux


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
            self.assertEqual(len(lines), 1)
            self.assertTrue(lines[0].startswith("Moya "))
            self.assertIn("#2 ", lines[0])
            self.assertIn("Here is the answer.", lines[0])
            self.assertNotIn("And another line.", " ".join(lines))
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
            self.assertNotIn("a private aside", spoken)
            self.assertNotIn("ask the other agent", spoken)
        finally:
            shutil.rmtree(root)

    def test_only_visible_chat_text_is_read(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.transcript.replicas.agent-123",
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"message","role":"user","seq":1,"timestampMs":1,"content":"user typed this"},'
                  '{"kind":"message","role":"assistant","seq":2,"timestampMs":2,"content":"reasoning that is not on screen"},'
                  '{"kind":"message","role":"system","seq":3,"timestampMs":3,"content":"system turn"},'
                  '{"kind":"message","role":"assistant","id":"tool-1","seq":4,"timestampMs":4,"content":"tool result payload"},'
                  '{"kind":"event","seq":5,"timestampMs":5,"event":{"type":"status","text":"still working"}},'
                  '{"kind":"send-message","seq":6,"timestampMs":6,"message":{"type":"widget","content":"a button"}},'
                  '{"kind":"send-message","seq":7,"timestampMs":7,"message":{"type":"todo","content":"finish the list"}},'
                  '{"kind":"send-message","seq":8,"timestampMs":8,"message":{"type":"tool","content":"ran a command"}},'
                  '{"kind":"send-message","id":"hid","hidden":true,"seq":9,"timestampMs":9,"message":{"type":"text","content":"hidden bubble"}},'
                  '{"kind":"send-message","id":"agent-outbound-4","toAgent":{"id":"other"},"seq":10,"timestampMs":10,"message":{"type":"text","content":"note to another agent"}},'
                  '{"kind":"send-message","id":"shown","seq":11,"timestampMs":11,"message":{"type":"text","content":"See [the docs](https://example.com/secret)."}}'
                  ']}}')
            lines, _names = grok_store.reply_lines(store)
            spoken = " ".join(lines)
            self.assertEqual(len(lines), 1)
            self.assertIn("See the docs.", spoken)
            self.assertNotIn("example.com", spoken)
            for hidden in (
                "user typed", "reasoning", "system turn", "tool result", "still working",
                "a button", "finish the list", "ran a command", "hidden bubble", "note to another agent",
            ):
                self.assertNotIn(hidden, spoken)
        finally:
            shutil.rmtree(root)

    def test_a_replaced_blob_does_not_swallow_the_new_replies(self):
        path = os.path.join("store", "moya.blob")
        kept, misses = grok_store.hold_open_file(path, False, None, 0)
        self.assertEqual(kept, path)
        self.assertEqual(misses, 1)
        kept, misses = grok_store.hold_open_file(kept, True, path, misses)
        self.assertEqual((kept, misses), (path, 0))
        history = ["Moya 9:24:54 AM #2 The fix for reading the newest reply is being built."]
        seen = set()
        grok_store.mark_seen(seen, [["id:r2", "h:old"]])
        lines = history + [
            "Moya 9:25:59 AM #3 Good news. Just to check.",
            "Moya 9:26:54 AM #4 Got it. It reads one new reply.",
        ]
        keys = [["id:r2", "h:old"], ["id:r3", "h:a"], ["id:r4", "h:b"]]
        # The id from before the replace is already known. The two new ones are not.
        seen.update(["id:r2", "h:old"])
        fresh = grok_store.merge_open_replies(history, seen, lines, keys)
        self.assertEqual(len(fresh), 2)
        self.assertIn("Good news", fresh[0])
        self.assertIn("Got it", fresh[1])

    def test_two_quick_replies_during_playback_stay_in_order(self):
        """Two new replies land in the open file while Back is holding an older line."""
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            key = "sand.client.slice.account.a.transcript.replicas.moya"
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya","selected":true}]}}')
            _blob(store, key,
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"send-message","id":"r1","seq":1,"timestampMs":1700000001000,"message":{"type":"text","content":"Yes, it will work in Edge too."}},'
                  '{"kind":"send-message","id":"r2","seq":2,"timestampMs":1700000002000,"message":{"type":"text","content":"The fix for reading the newest reply is being built."}}'
                  ']}}')
            lines, _names, keylists, active = grok_store.reply_snapshot(store)
            seen = set()
            grok_store.mark_seen(seen, keylists)
            history = list(lines)
            pos = len(history) - 1
            path = _blob(store, key,
                         '{"schemaVersion":1,"value":{"entries":['
                         '{"kind":"send-message","id":"r1","seq":1,"timestampMs":1700000001000,"message":{"type":"text","content":"Yes, it will work in Edge too."}},'
                         '{"kind":"send-message","id":"r2","seq":2,"timestampMs":1700000002000,"message":{"type":"text","content":"The fix for reading the newest reply is being built."}},'
                         '{"kind":"send-message","id":"r3","seq":3,"timestampMs":1700000003000,"message":{"type":"text","content":"Good news. Just to check\\u2026"}},'
                         '{"kind":"send-message","id":"r4","seq":4,"timestampMs":1700000004000,"message":{"type":"text","content":"Got it. It reads one new reply."}}'
                         ']}}')
            self.assertTrue(path.endswith(".blob"))
            self.assertEqual(active, path)
            lines, _names, keylists, still = grok_store.reply_snapshot(store)
            self.assertEqual(still, active)
            fresh = grok_store.merge_open_replies(history, seen, lines, keylists)
            self.assertEqual(len(fresh), 2)
            self.assertIn("Good news", fresh[0])
            self.assertIn("Got it", fresh[1])
            self.assertEqual(history[-2:], fresh)
            self.assertLess(pos, len(history) - 1)
            stepped = pos
            heard = []
            while stepped < len(history) - 1:
                stepped += 1
                heard.append(history[stepped])
            self.assertEqual(heard, fresh)
            self.assertIn("Got it", heard[-1])
            self.assertEqual(grok_store.merge_open_replies(history, seen, lines, keylists), [])
        finally:
            shutil.rmtree(root)

    def test_speech_matches_the_screen(self):
        self.assertEqual(grok_store.render_speech("See [the docs](https://example.com/path)."), "See the docs.")
        self.assertNotIn("example.com", grok_store.render_speech("[label](https://example.com/path)"))
        self.assertEqual(grok_store.render_speech("**bold** and *italic* and `code`"), "bold and italic and code")
        self.assertEqual(grok_store.render_speech("- one\n- two"), "one. two")
        spoken = grok_store.render_speech("Before\n```python\nprint(1)\n```\nAfter")
        self.assertIn("code block", spoken)
        self.assertNotIn("print", spoken)
        self.assertIn("Before", spoken)
        self.assertIn("After", spoken)
        self.assertEqual(grok_store.plain_label("A\U0001F916 CAD/CAM"), "A CAD/CAM")
        self.assertEqual(grok_store.plain_label("A? CAD/CAM"), "A CAD/CAM")
        self.assertNotIn("\U0001F916", grok_store.render_speech("See \U0001F916 this"))
        spoken_once = set()
        self.assertTrue(grok_store.allow_auto_speech(spoken_once, "The same reply"))
        self.assertFalse(grok_store.allow_auto_speech(spoken_once, "The same reply"))
        self.assertTrue(grok_store.allow_auto_speech(spoken_once, "The same reply", replay=True))

    def test_message_id_survives_rewrite_and_chat_switch(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"larry","name":"Larry","selected":true},{"id":"amy","name":"Amy"}]}}')
            larry_key = "sand.client.slice.account.a.transcript.replicas.larry"
            amy_key = "sand.client.slice.account.a.transcript.replicas.amy"
            _blob(store, larry_key,
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"message","role":"user","id":"u1","seq":1,"timestampMs":1000,"content":"hi"},'
                  '{"kind":"send-message","id":"same-1","seq":2,"timestampMs":1100,"message":{"type":"text","content":"Spoken once."}}'
                  ']}}')
            _blob(store, amy_key,
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"message","role":"user","id":"u2","seq":1,"timestampMs":500,"content":"amy hi"},'
                  '{"kind":"send-message","id":"amy-1","seq":2,"timestampMs":600,"message":{"type":"text","content":"Amy was quiet."}}'
                  ']}}')
            lines, _names, keylists, active = grok_store.reply_snapshot(store)
            self.assertIn("Spoken once.", " ".join(lines))
            self.assertNotIn("Amy was quiet.", " ".join(lines))
            seen = set()
            grok_store.mark_seen(seen, keylists)
            # Eight minutes later the same bubble is rewritten with a new time and seq.
            _blob(store, larry_key,
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"message","role":"user","id":"u1","seq":1,"timestampMs":1000,"content":"hi"},'
                  '{"kind":"send-message","id":"same-1","seq":40,"timestampMs":999999,"message":{"type":"text","content":"Spoken once."}}'
                  ']}}')
            lines, _names, keylists, active2 = grok_store.reply_snapshot(store)
            self.assertEqual(active, active2)
            self.assertEqual(grok_store.unseen_lines(seen, lines, keylists), [])
            # Switch to Amy, then back. Larry's id is still known.
            roster = _blob(store, "sand.client.slice.account.a.roster.last-roster",
                           '{"schemaVersion":1,"value":{"rows":[{"id":"larry","name":"Larry"},{"id":"amy","name":"Amy","selected":true}]}}')
            os.utime(roster, (2_000_000_000, 2_000_000_000))
            lines, _names, keylists, _active = grok_store.reply_snapshot(store)
            fresh = grok_store.unseen_lines(seen, lines, keylists)
            self.assertEqual(len(fresh), 1)
            self.assertIn("Amy was quiet.", fresh[0])
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"larry","name":"Larry","selected":true},{"id":"amy","name":"Amy"}]}}')
            _blob(store, larry_key,
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"send-message","id":"same-1","seq":41,"timestampMs":1000001,"message":{"id":"same-1","type":"text","content":"Spoken once."}}'
                  ']}}')
            lines, _names, keylists, _active = grok_store.reply_snapshot(store)
            self.assertEqual(grok_store.unseen_lines(seen, lines, keylists), [])
            # A new id with the same on-screen words is still the same reply.
            _blob(store, larry_key,
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"send-message","id":"brand-new","seq":42,"timestampMs":1000002,"message":{"type":"text","content":"Spoken once."}}'
                  ']}}')
            lines, _names, keylists, _active = grok_store.reply_snapshot(store)
            self.assertEqual(grok_store.unseen_lines(seen, lines, keylists), [])
        finally:
            shutil.rmtree(root)

    def test_restart_with_existing_history_reads_nothing_until_a_new_reply(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            key = "sand.client.slice.account.a.transcript.replicas.agent-123"
            _blob(store, key,
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"message","role":"assistant","id":"note-a","toAgent":{"id":"cloud"},"seq":1,"timestampMs":1700000000000,"content":"to another agent"},'
                  '{"kind":"message","role":"assistant","id":"agent-outbound-2","seq":2,"timestampMs":1700000000500,"content":"outbound note"},'
                  '{"kind":"send-message","id":"old-1","seq":3,"timestampMs":1700000001000,"message":{"type":"text","content":"older reply"}},'
                  '{"kind":"send-message","id":"old-2","seq":4,"timestampMs":1700000002000,"message":{"type":"text","content":"newest already here"}}'
                  ']}}')
            lines, _names, keylists, _active = grok_store.reply_snapshot(store)
            spoken = " ".join(lines)
            self.assertIn("older reply", spoken)
            self.assertIn("newest already here", spoken)
            self.assertNotIn("to another agent", spoken)
            self.assertNotIn("outbound note", spoken)
            # A fresh process baselines whatever is already saved.
            seen = set()
            grok_store.mark_seen(seen, keylists)
            self.assertEqual(grok_store.unseen_lines(seen, lines, keylists), [])
            # Restarting does the same with a new seen set. History is still quiet.
            lines, _names, keylists, _active = grok_store.reply_snapshot(store)
            seen = set()
            grok_store.mark_seen(seen, keylists)
            self.assertEqual(grok_store.unseen_lines(seen, lines, keylists), [])
            self.assertTrue(grok_store.launch_is_baseline(set(), ["Bot older reply", "Bot newest already here"], []))
            self.assertFalse(grok_store.launch_is_baseline(seen, lines, lines))
            # The slice is rewritten and a reply arrives after launch.
            _blob(store, key,
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"message","role":"assistant","id":"agent-outbound-2","seq":1,"timestampMs":1700000000500,"content":"outbound note"},'
                  '{"kind":"send-message","id":"old-1","seq":8,"timestampMs":1700000001000,"message":{"type":"text","content":"older reply"}},'
                  '{"kind":"send-message","id":"old-2","seq":9,"timestampMs":1700000002000,"message":{"type":"text","content":"newest already here"}},'
                  '{"kind":"send-message","id":"new-1","seq":10,"timestampMs":1700000003000,"message":{"type":"text","content":"arrived after launch"}}'
                  ']}}')
            lines, _names, keylists, _active = grok_store.reply_snapshot(store)
            fresh = grok_store.unseen_lines(seen, lines, keylists)
            self.assertEqual(len(fresh), 1)
            self.assertIn("arrived after launch", fresh[0])
            self.assertNotIn("older reply", " ".join(fresh))
            self.assertNotIn("newest already here", " ".join(fresh))
            self.assertNotIn("outbound note", " ".join(lines))
            self.assertIn("older reply", " ".join(lines))
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

    def _two_chats(self, root, larry_user_ms, amy_user_ms):
        store = os.path.join(root, "sand-client-persistence")
        _blob(store, "sand.client.slice.account.a.roster.last-roster",
              '{"schemaVersion":1,"value":{"rows":[{"id":"larry","name":"Larry"},{"id":"amy","name":"Amy"}]}}')
        larry = _blob(store, "sand.client.slice.account.a.transcript.replicas.larry",
                      '{"schemaVersion":1,"value":{"entries":['
                      '{"kind":"message","role":"user","id":"u-larry","seq":1,"timestampMs":%s,"content":"question for larry"},'
                      '{"kind":"send-message","id":"r-larry","seq":2,"timestampMs":1700000009000,"message":{"type":"text","content":"larry reply"}},'
                      '{"kind":"message","role":"assistant","id":"agent-outbound-larry","toAgent":{"id":"amy"},"seq":3,"timestampMs":1700000009500,"content":"larry side note"}'
                      ']}}' % larry_user_ms)
        amy = _blob(store, "sand.client.slice.account.a.transcript.replicas.amy",
                    '{"schemaVersion":1,"value":{"entries":['
                    '{"kind":"message","role":"user","id":"u-amy","seq":1,"timestampMs":%s,"content":"question for amy"},'
                    '{"kind":"send-message","id":"r-amy","seq":2,"timestampMs":1700000008000,"message":{"type":"text","content":"amy reply"}}'
                    ']}}' % amy_user_ms)
        return store, larry, amy

    def test_open_chat_ignores_other_bots(self):
        root = tempfile.mkdtemp()
        try:
            store, larry_file, amy_file = self._two_chats(root, 1_700_000_000_000, 1_800_000_000_000)
            # Neither file was rewritten after its last message, and nothing
            # names the open bot. Do not guess from who was typed to last.
            os.utime(amy_file, (1_800_000_000, 1_800_000_000))
            os.utime(larry_file, (1_700_000_009, 1_700_000_009))
            lines, _names, _keys, active = grok_store.reply_snapshot(
                store, window_titles=["Grok Bot", "Amy — Grok Bot"])
            self.assertIn("amy reply", " ".join(lines))
            self.assertNotIn("larry reply", " ".join(lines))
            self.assertIn("amy reply", grok_store.latest_replay(lines))
            self.assertTrue(active.endswith(grok_store.encode_base32(
                "sand.client.slice.account.a.transcript.replicas.amy") + ".blob"))
            # A saved selection names the open chat when the title does not.
            _blob(store, "sand.client.slice.account.a.ui.selected-agent",
                  '{"schemaVersion":1,"value":{"selectedAgentId":"larry"}}')
            lines, _names = grok_store.reply_lines(store)
            spoken = " ".join(lines)
            self.assertIn("larry reply", spoken)
            self.assertNotIn("amy reply", spoken)
            self.assertNotIn("larry side note", spoken)
            os.remove(os.path.join(store, grok_store.encode_base32("sand.client.slice.account.a.ui.selected-agent") + ".blob"))
            lines, _names, _keys, active = grok_store.reply_snapshot(store, window_titles=["Larry — Grok Bot"])
            self.assertIn("larry reply", " ".join(lines))
            self.assertNotIn("amy reply", " ".join(lines))
            self.assertIsNotNone(active)
            # A roster row marked selected also names the open chat.
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"larry","name":"Larry","selected":true},{"id":"amy","name":"Amy"}]}}')
            lines, _names = grok_store.reply_lines(store)
            spoken = " ".join(lines)
            self.assertIn("larry reply", spoken)
            self.assertNotIn("amy reply", spoken)
        finally:
            shutil.rmtree(root)

    def test_bot_switch_follows_the_open_window_and_does_not_reread_it(self):
        root = tempfile.mkdtemp()
        try:
            store, _larry, amy_file = self._two_chats(root, 1_900_000_000_000, 1_700_000_000_000)
            # Larry was typed to last. The saved current bot is Amy, and the
            # previous bot is also recorded. Only Amy is open.
            _blob(store, "sand.client.slice.account.a.ui.selected-agent",
                  '{"schemaVersion":1,"value":{"selectedAgentId":"amy","lastSelectedAgentId":"larry"}}')
            lines, _names, _keys, _active = grok_store.reply_snapshot(store)
            self.assertIn("amy reply", " ".join(lines))
            self.assertNotIn("larry reply", " ".join(lines))
            # The saved selection is still Larry, but the window has moved to Amy.
            selection = _blob(store, "sand.client.slice.account.a.ui.selected-agent",
                              '{"schemaVersion":1,"value":{"selectedAgentId":"larry","lastSelectedAgentId":"amy"}}')
            os.utime(selection, (1_000, 1_000))
            lines, _names, keys, previous = grok_store.reply_snapshot(store, window_titles=["Amy — Grok Bot"])
            spoken = " ".join(lines)
            self.assertIn("amy reply", spoken)
            self.assertNotIn("larry reply", spoken)
            seen = set()
            grok_store.mark_seen(seen, keys)
            self.assertEqual(grok_store.unseen_lines(seen, lines, keys), [])
            with open(amy_file, "w", encoding="utf-8") as handle:
                handle.write('{"schemaVersion":1,"value":{"entries":['
                             '{"kind":"message","role":"user","id":"u-amy","seq":1,"timestampMs":1700000000000,"content":"question for amy"},'
                             '{"kind":"send-message","id":"r-amy","seq":2,"timestampMs":1700000008000,"message":{"type":"text","content":"amy reply"}},'
                             '{"kind":"send-message","id":"r-amy-new","seq":3,"timestampMs":1700000010000,"message":{"type":"text","content":"just arrived"}}'
                             ']}}')
            lines, _names, keys, active = grok_store.reply_snapshot(store, window_titles=["Amy — Grok Bot"])
            self.assertEqual(active, previous)
            fresh = grok_store.unseen_lines(seen, lines, keys)
            self.assertEqual(len(fresh), 1)
            self.assertIn("just arrived", fresh[0])
            self.assertNotIn("amy reply", " ".join(fresh))
        finally:
            shutil.rmtree(root)

    def test_account_switch_drops_the_old_session(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            home_chat = _blob(store, "sand.client.slice.account.grok|user_home.transcript.replicas.larry",
                              '{"schemaVersion":1,"value":{"entries":['
                              '{"kind":"message","role":"user","id":"u-home","seq":1,"timestampMs":1900000000000,"content":"home question"},'
                              '{"kind":"send-message","id":"r-home","seq":2,"timestampMs":1900000001000,"message":{"type":"text","content":"home reply"}}'
                              ']}}')
            home_selection = _blob(store, "sand.client.slice.account.grok|user_home.ui.selected-agent",
                                   '{"schemaVersion":1,"value":{"selectedAgentId":"larry"}}')
            _blob(store, "sand.client.slice.account.grok|user_work.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"payroll","name":"Payroll"}]}}')
            _blob(store, "sand.client.slice.account.grok|user_work.transcript.replicas.payroll",
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"message","role":"user","id":"u-work","seq":1,"timestampMs":1800000000000,"content":"work question"},'
                  '{"kind":"send-message","id":"r-work","seq":2,"timestampMs":1800000001000,"message":{"type":"text","content":"work reply"}}'
                  ']}}')
            work_roster = os.path.join(store, grok_store.encode_base32(
                "sand.client.slice.account.grok|user_work.roster.last-roster") + ".blob")
            os.utime(home_selection, (1_000, 1_000))
            os.utime(work_roster, (5_000, 5_000))
            os.utime(home_chat, (9_000, 9_000))
            lines, _names, keys, active = grok_store.reply_snapshot(store)
            spoken = " ".join(lines)
            self.assertIn("work reply", spoken)
            self.assertNotIn("home reply", spoken)
            # A later write from the old account's bot is not the open chat.
            os.utime(home_chat, (20_000, 20_000))
            lines, _names, _keys, still = grok_store.reply_snapshot(store)
            self.assertEqual(still, active)
            self.assertIn("work reply", " ".join(lines))
            self.assertNotIn("home reply", " ".join(lines))
            seen = set()
            grok_store.mark_seen(seen, keys)
            self.assertEqual(grok_store.unseen_lines(seen, lines, keys), [])
        finally:
            shutil.rmtree(root)

    def test_account_switch_can_be_a_different_folder(self):
        root = tempfile.mkdtemp()
        try:
            home = os.path.join(root, "home", "sand-client-persistence")
            work = os.path.join(root, "work", "sand-client-persistence")
            _blob(home, "sand.client.slice.account.grok|user_home.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"larry","name":"Larry"}]}}')
            _blob(home, "sand.client.slice.account.grok|user_home.transcript.replicas.larry",
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"send-message","id":"r-home","seq":1,"timestampMs":1900000000000,"message":{"type":"text","content":"home reply"}}'
                  ']}}')
            home_selection = _blob(home, "sand.client.slice.account.grok|user_home.ui.selected-agent",
                                   '{"schemaVersion":1,"value":{"selectedAgentId":"larry"}}')
            home_roster = os.path.join(home, grok_store.encode_base32(
                "sand.client.slice.account.grok|user_home.roster.last-roster") + ".blob")
            _blob(work, "sand.client.slice.account.grok|user_work.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"payroll","name":"Payroll"}]}}')
            _blob(work, "sand.client.slice.account.grok|user_work.transcript.replicas.payroll",
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"send-message","id":"r-work","seq":1,"timestampMs":1800000000000,"message":{"type":"text","content":"work reply"}}'
                  ']}}')
            os.utime(home_selection, (1_000, 1_000))
            os.utime(home_roster, (1_000, 1_000))
            os.utime(os.path.join(work, grok_store.encode_base32(
                "sand.client.slice.account.grok|user_work.roster.last-roster") + ".blob"), (5_000, 5_000))
            lines, _names, _keys, _active = grok_store.reply_snapshot(None, directories=[home, work])
            self.assertIn("work reply", " ".join(lines))
            self.assertNotIn("home reply", " ".join(lines))
            # A window title must not pull the reader onto the other account.
            os.utime(home_selection, (9_000, 9_000))
            lines, _names, _keys, _active = grok_store.reply_snapshot(
                None, window_titles=["Payroll — Grok Bot", "Grok Bot"], directories=[home, work])
            self.assertIn("home reply", " ".join(lines))
            self.assertNotIn("work reply", " ".join(lines))
        finally:
            shutil.rmtree(root)

    def test_back_after_a_bot_switch_plays_that_bots_last_reply(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"},{"id":"cameron","name":"Cameron"}]}}')
            _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}}'
                  ']}}')
            cameron = _blob(store, "sand.client.slice.account.a.transcript.replicas.cameron",
                            '{"schemaVersion":1,"value":{"persistedAt":1800000000000,"entries":['
                            '{"kind":"send-message","id":"r-cameron-old","seq":1,"timestampMs":1700000001000,"message":{"type":"text","content":"cameron older"}},'
                            '{"kind":"send-message","id":"r-cameron","seq":2,"timestampMs":1700000002000,"message":{"type":"text","content":"cameron last reply"}}'
                            ']}}')
            selection = _blob(store, "sand.client.slice.account.a.ui.selected-agent",
                              '{"schemaVersion":1,"value":{"selectedAgentId":"moya","lastSelectedAgentId":"cameron"}}')
            os.utime(selection, (1_700_000_000, 1_700_000_000))
            os.utime(cameron, (1_700_000_002, 1_700_000_002))
            # Selection says Moya. Cameron's file being rewritten is not a switch.
            # A title that names Cameron is the bot on screen, and Back plays his latest.
            for titles, needle, other in (
                (["Grok Bot"], "moya reply", "cameron"),
                (None, "moya reply", "cameron"),
                (["Cameron — Grok Bot"], "cameron last reply", "moya reply"),
            ):
                lines, _names, _keys, active = grok_store.reply_snapshot(store, window_titles=titles)
                played = grok_store.latest_replay(lines)
                self.assertIn(needle, played)
                self.assertNotIn(other, played.lower() if other == "cameron" else played)
                self.assertNotIn("cameron older", played or "")
            # Two chats rewritten together, and no saved selection: not sure, so Back says nothing.
            os.remove(selection)
            moya = os.path.join(store, grok_store.encode_base32(
                "sand.client.slice.account.a.transcript.replicas.moya") + ".blob")
            with open(moya, "w", encoding="utf-8") as handle:
                handle.write('{"schemaVersion":1,"value":{"persistedAt":1800000002000,"entries":['
                             '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}}'
                             ']}}')
            lines, _names, _keys, active = grok_store.reply_snapshot(store, window_titles=["Grok Bot"])
            self.assertEqual(lines, [])
            self.assertIsNone(active)
            self.assertIsNone(grok_store.latest_replay(lines))
        finally:
            shutil.rmtree(root)

    def test_a_background_reply_does_not_steal_the_open_chat(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"},{"id":"cameron","name":"Cameron"}]}}')
            _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                  '{"schemaVersion":1,"value":{"entries":['
                  '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}}'
                  ']}}')
            # Cameron just replied. The file time matches the message, so this is not an open.
            cameron = _blob(store, "sand.client.slice.account.a.transcript.replicas.cameron",
                            '{"schemaVersion":1,"value":{"entries":['
                            '{"kind":"send-message","id":"r-cameron","seq":1,"timestampMs":1800000000000,"message":{"type":"text","content":"cameron background"}}'
                            ']}}')
            os.utime(cameron, (1_800_000_000, 1_800_000_000))
            _blob(store, "sand.client.slice.account.a.ui.selected-agent",
                  '{"schemaVersion":1,"value":{"selectedAgentId":"moya"}}')
            lines, _names, _keys, _active = grok_store.reply_snapshot(store, window_titles=["Grok Bot"])
            self.assertIn("moya reply", " ".join(lines))
            self.assertNotIn("cameron background", " ".join(lines))
            watched, _names, keys, active, skipped = grok_store.watch_snapshot(store, seen=set(), follow_path=None)
            self.assertEqual(active, _active)
            self.assertIn("moya reply", " ".join(watched))
            self.assertNotIn("cameron background", " ".join(watched))
            self.assertTrue(any(reason == "not the open chat" for _keys, reason, _line in skipped))
        finally:
            shutil.rmtree(root)

    def _append_reply(self, path, payload, mtime):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.utime(path, (mtime, mtime))

    def test_a_synced_open_does_not_hide_the_chat_that_just_replied(self):
        """Another device rewrites an idle chat. This window is the one that just changed."""
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"},{"id":"cameron","name":"Cameron"}]}}')
            moya = _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                         '{"schemaVersion":1,"value":{"entries":['
                         '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}}'
                         ']}}')
            cameron = _blob(store, "sand.client.slice.account.a.transcript.replicas.cameron",
                            '{"schemaVersion":1,"value":{"entries":['
                            '{"kind":"send-message","id":"r-cameron","seq":1,"timestampMs":1600000000000,"message":{"type":"text","content":"cameron old"}}'
                            ']}}')
            selection = _blob(store, "sand.client.slice.account.a.ui.selected-agent",
                              '{"schemaVersion":1,"value":{"selectedAgentId":"moya"}}')
            os.utime(selection, (1_700_000_050, 1_700_000_050))
            # Cameron's file jumped without a new message. That used to become "the open chat".
            os.utime(cameron, (1_700_000_100, 1_700_000_100))
            os.utime(moya, (1_700_000_000, 1_700_000_000))
            seen = set()
            grok_store.mark_seen(seen, grok_store.every_reply_keylists(store))
            self._append_reply(
                moya,
                '{"schemaVersion":1,"value":{"entries":['
                '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}},'
                '{"kind":"send-message","id":"r-new","seq":2,"timestampMs":1700000200000,"message":{"type":"text","content":"moya just arrived"}}'
                ']}}',
                1_700_000_200)
            lines, _names, _keys, active = grok_store.reply_snapshot(store)
            self.assertIn("moya just arrived", " ".join(lines))
            self.assertNotIn("cameron old", " ".join(lines))
            self.assertTrue(active.endswith(grok_store.encode_base32(
                "sand.client.slice.account.a.transcript.replicas.moya") + ".blob"))
            self.assertIn("Moya", grok_store.open_chat_line())
            self.assertIn("selection", grok_store.open_chat_line())
            watched, _names, keys, path, skipped = grok_store.watch_snapshot(
                store, seen=seen, follow_path=None)
            self.assertEqual(path, active)
            fresh = grok_store.unseen_lines(seen, watched, keys)
            self.assertTrue(any("moya just arrived" in line for line in fresh), fresh)
            self.assertFalse(any(reason == "not the open chat" and "moya just arrived" in line
                                 for _keys, reason, line in skipped))
            again = grok_store.open_chat_line()
            grok_store.reply_snapshot(store)
            self.assertEqual(grok_store.open_chat_line(), again)
        finally:
            shutil.rmtree(root)

    def test_last_opened_from_another_device_does_not_hide_the_live_chat(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"},{"id":"cameron","name":"Cameron"}]}}')
            moya = _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                         '{"schemaVersion":1,"value":{"entries":['
                         '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}}'
                         ']}}')
            cameron = _blob(store, "sand.client.slice.account.a.transcript.replicas.cameron",
                            '{"schemaVersion":1,"value":{"entries":['
                            '{"kind":"send-message","id":"r-cameron","seq":1,"timestampMs":1700000001000,"message":{"type":"text","content":"cameron reply"}}'
                            ']}}')
            last = _blob(store, "sand.client.slice.account.a.ui.last-opened",
                         '{"schemaVersion":1,"value":{"selectedAgentId":"cameron"}}')
            os.utime(cameron, (1_700_000_010, 1_700_000_010))
            os.utime(last, (1_700_000_020, 1_700_000_020))
            os.utime(moya, (1_700_000_000, 1_700_000_000))
            seen = set()
            grok_store.mark_seen(seen, grok_store.every_reply_keylists(store))
            self._append_reply(
                moya,
                '{"schemaVersion":1,"value":{"entries":['
                '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}},'
                '{"kind":"send-message","id":"r-new","seq":2,"timestampMs":1700000300000,"message":{"type":"text","content":"moya just arrived"}}'
                ']}}',
                1_700_000_300)
            watched, _names, keys, path, skipped = grok_store.watch_snapshot(store, seen=seen, follow_path=None)
            fresh = grok_store.unseen_lines(seen, watched, keys)
            self.assertTrue(any("moya just arrived" in line for line in fresh), (fresh, skipped, grok_store.open_chat_line()))
            self.assertFalse(any("moya just arrived" in line and reason == "not the open chat"
                                 for _keys, reason, line in skipped))
            self.assertTrue(path.endswith(grok_store.encode_base32(
                "sand.client.slice.account.a.transcript.replicas.moya") + ".blob"))
        finally:
            shutil.rmtree(root)

    def test_a_background_reply_stays_quiet_when_selection_names_the_open_chat(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"},{"id":"cameron","name":"Cameron"}]}}')
            moya = _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                         '{"schemaVersion":1,"value":{"entries":['
                         '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}}'
                         ']}}')
            cameron = _blob(store, "sand.client.slice.account.a.transcript.replicas.cameron",
                            '{"schemaVersion":1,"value":{"entries":['
                            '{"kind":"send-message","id":"r-cameron","seq":1,"timestampMs":1700000100000,"message":{"type":"text","content":"cameron background"}}'
                            ']}}')
            selection = _blob(store, "sand.client.slice.account.a.ui.selected-agent",
                              '{"schemaVersion":1,"value":{"selectedAgentId":"moya"}}')
            os.utime(moya, (1_700_000_000, 1_700_000_000))
            os.utime(selection, (1_700_000_010, 1_700_000_010))
            os.utime(cameron, (1_700_000_100, 1_700_000_100))
            watched, _names, _keys, active, skipped = grok_store.watch_snapshot(store, seen=set(), follow_path=None)
            self.assertTrue(active.endswith(grok_store.encode_base32(
                "sand.client.slice.account.a.transcript.replicas.moya") + ".blob"), grok_store.open_chat_line())
            self.assertTrue(any(reason == "not the open chat" and "cameron background" in line
                                for _keys, reason, line in skipped), skipped)
            self.assertFalse(any("cameron background" in line for line in watched))
        finally:
            shutil.rmtree(root)

    def test_new_reply_is_spoken_when_the_open_chat_is_not_marked(self):
        """Mint regression: blobs update, but nothing is spoken and no speak line is logged.

        Two chats, no saved selection, and the file time matches the newest
        message. That is a normal reply, not a chat being opened, so the strict
        snapshot stays empty. v1.3.3 then dropped the reply. The file is re-read
        (the mtime changed) and the words are not an already-spoken duplicate.
        """
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"},{"id":"cameron","name":"Cameron"}]}}')
            moya = _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                         '{"schemaVersion":1,"value":{"entries":['
                         '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}}'
                         ']}}')
            cameron = _blob(store, "sand.client.slice.account.a.transcript.replicas.cameron",
                            '{"schemaVersion":1,"value":{"entries":['
                            '{"kind":"send-message","id":"r-cameron","seq":1,"timestampMs":1700000010000,"message":{"type":"text","content":"cameron reply"}}'
                            ']}}')
            os.utime(moya, (1_700_000_000, 1_700_000_000))
            os.utime(cameron, (1_700_000_010, 1_700_000_010))
            lines, _names, _keys, active = grok_store.reply_snapshot(store, window_titles=["Grok Bot"])
            self.assertEqual(lines, [])
            self.assertIsNone(active)
            seen = set()
            grok_store.mark_seen(seen, grok_store.every_reply_keylists(store))
            self._append_reply(
                cameron,
                '{"schemaVersion":1,"value":{"entries":['
                '{"kind":"send-message","id":"r-cameron","seq":1,"timestampMs":1700000010000,"message":{"type":"text","content":"cameron reply"}},'
                '{"kind":"send-message","id":"r-new","seq":2,"timestampMs":1700000100000,"message":{"type":"text","content":"just arrived"}}'
                ']}}',
                1_700_000_100)
            parsed = grok_store._parsed_json(cameron)
            self.assertIn("just arrived", json.dumps(parsed))
            lines, _names, _keys, active = grok_store.reply_snapshot(store, window_titles=["Grok Bot"])
            self.assertEqual(lines, [])
            self.assertIsNone(active)
            watched, _names, keys, path, skipped = grok_store.watch_snapshot(
                store, window_titles=["Grok Bot"], seen=seen, follow_path=None)
            self.assertEqual(skipped, [])
            self.assertTrue(path.endswith(".blob"))
            fresh = grok_store.unseen_lines(seen, watched, keys)
            self.assertEqual(len(fresh), 1)
            self.assertIn("just arrived", fresh[0])
            self.assertNotIn("cameron reply", " ".join(fresh))
            spoken = set()
            self.assertTrue(grok_store.allow_auto_speech(spoken, "just arrived"))
            self.assertIn("open chat unclear", grok_store.skip_log("open chat unclear", fresh[0]))
        finally:
            shutil.rmtree(root)

    def test_reply_keeps_the_chat_after_the_open_signal_drops(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"},{"id":"cameron","name":"Cameron"}]}}')
            moya = _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                         '{"schemaVersion":1,"value":{"entries":['
                         '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}}'
                         ']}}')
            cameron = _blob(store, "sand.client.slice.account.a.transcript.replicas.cameron",
                            '{"schemaVersion":1,"value":{"persistedAt":1700000010000,"entries":['
                            '{"kind":"send-message","id":"r-cameron","seq":1,"timestampMs":1700000010000,"message":{"type":"text","content":"cameron reply"}}'
                            ']}}')
            os.utime(moya, (1_700_000_000, 1_700_000_000))
            # Cameron's file was saved long after its last message: the chat was opened.
            os.utime(cameron, (1_700_000_040, 1_700_000_040))
            lines, _names, keys, active = grok_store.reply_snapshot(store, window_titles=["Grok Bot"])
            self.assertIn("cameron reply", " ".join(lines))
            self.assertNotIn("moya", " ".join(lines).lower())
            seen = set()
            grok_store.mark_seen(seen, keys)
            grok_store.mark_seen(seen, grok_store.every_reply_keylists(store))
            # The new reply's file time matches the message, so it no longer looks opened.
            self._append_reply(
                cameron,
                '{"schemaVersion":1,"value":{"persistedAt":1700000100000,"entries":['
                '{"kind":"send-message","id":"r-cameron","seq":1,"timestampMs":1700000010000,"message":{"type":"text","content":"cameron reply"}},'
                '{"kind":"send-message","id":"r-new","seq":2,"timestampMs":1700000100000,"message":{"type":"text","content":"just arrived"}}'
                ']}}',
                1_700_000_100)
            lines, _names, _keys, still = grok_store.reply_snapshot(store, window_titles=["Grok Bot"])
            self.assertEqual(lines, [])
            self.assertIsNone(still)
            watched, _names, keys, path, skipped = grok_store.watch_snapshot(
                store, window_titles=["Grok Bot"], seen=seen, follow_path=active)
            self.assertEqual(path, active)
            self.assertEqual(skipped, [])
            fresh = grok_store.unseen_lines(seen, watched, keys)
            self.assertEqual(len(fresh), 1)
            self.assertIn("just arrived", fresh[0])
        finally:
            shutil.rmtree(root)

    def test_two_new_replies_are_skipped_when_the_open_chat_is_unclear(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"},{"id":"cameron","name":"Cameron"}]}}')
            moya = _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                         '{"schemaVersion":1,"value":{"entries":['
                         '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}}'
                         ']}}')
            cameron = _blob(store, "sand.client.slice.account.a.transcript.replicas.cameron",
                            '{"schemaVersion":1,"value":{"entries":['
                            '{"kind":"send-message","id":"r-cameron","seq":1,"timestampMs":1700000010000,"message":{"type":"text","content":"cameron reply"}}'
                            ']}}')
            os.utime(moya, (1_700_000_000, 1_700_000_000))
            os.utime(cameron, (1_700_000_010, 1_700_000_010))
            seen = set()
            grok_store.mark_seen(seen, grok_store.every_reply_keylists(store))
            self._append_reply(
                moya,
                '{"schemaVersion":1,"value":{"entries":['
                '{"kind":"send-message","id":"r-moya","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"moya reply"}},'
                '{"kind":"send-message","id":"r-moya-new","seq":2,"timestampMs":1700000200000,"message":{"type":"text","content":"moya just arrived"}}'
                ']}}',
                1_700_000_200)
            self._append_reply(
                cameron,
                '{"schemaVersion":1,"value":{"entries":['
                '{"kind":"send-message","id":"r-cameron","seq":1,"timestampMs":1700000010000,"message":{"type":"text","content":"cameron reply"}},'
                '{"kind":"send-message","id":"r-cameron-new","seq":2,"timestampMs":1700000201000,"message":{"type":"text","content":"cameron just arrived"}}'
                ']}}',
                1_700_000_201)
            watched, _names, _keys, path, skipped = grok_store.watch_snapshot(
                store, window_titles=["Grok Bot"], seen=seen, follow_path=None)
            self.assertEqual(watched, [])
            self.assertIsNone(path)
            reasons = [reason for _keys, reason, line in skipped]
            self.assertEqual(reasons, ["open chat unclear", "open chat unclear"])
            self.assertTrue(any("moya just arrived" in line for _keys, _reason, line in skipped))
            self.assertTrue(any("cameron just arrived" in line for _keys, _reason, line in skipped))
            self.assertTrue(grok_store.skip_log("open chat unclear", "cameron just arrived").startswith("skip new reply:"))
        finally:
            shutil.rmtree(root)

    def test_window_titles_include_the_open_bot(self):
        titles = grok_store.grok_titles_from_names([
            "Grokbot Voice", "Larry — Grok Bot", "Grok Bot", "Notepad",
        ])
        self.assertEqual(titles, ["Larry — Grok Bot", "Grok Bot"])
        self.assertIsNone(grok_store.agent_id_from_titles(["Grok Bot"], {"larry": "Larry"}))
        self.assertEqual(grok_store.agent_id_from_titles(titles, {"larry": "Larry", "amy": "Amy"}), "larry")

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

    def test_a_failed_chat_read_is_tried_again(self):
        """A locked blob must not be remembered as empty, or later replies stay silent."""
        root = tempfile.mkdtemp()
        real = grok_store._read_text
        try:
            store = os.path.join(root, "sand-client-persistence")
            path = _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                         '{"schemaVersion":1,"value":{"entries":['
                         '{"kind":"send-message","id":"r1","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"first reply"}}'
                         ']}}')
            grok_store._json_cache.clear()
            grok_store._read_problems.clear()
            self.assertIn("first reply", json.dumps(grok_store._parsed_json(path)))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"schemaVersion":1,"value":{"entries":['
                             '{"kind":"send-message","id":"r1","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"first reply"}},'
                             '{"kind":"send-message","id":"r2","seq":2,"timestampMs":1700000001000,"message":{"type":"text","content":"just arrived"}}'
                             ']}}')

            def locked(_path):
                raise OSError("locked")

            grok_store._read_text = locked
            self.assertIsNone(grok_store._parsed_json(path))
            self.assertTrue(any("OSError" in text for text in grok_store._read_problems.values()))
            self.assertIsNone(grok_store.note_read_problem(path, "OSError"))
            grok_store._read_text = real
            parsed = grok_store._parsed_json(path)
            self.assertIn("just arrived", json.dumps(parsed))
            self.assertEqual(grok_store._read_problems, {})
        finally:
            grok_store._read_text = real
            grok_store._json_cache.clear()
            grok_store._read_problems.clear()
            shutil.rmtree(root)

    def test_a_blob_deleted_between_list_and_read_does_not_stop_the_next_reply(self):
        """Grok Bot renames a temp file onto the blob. The missing name is skipped."""
        root = tempfile.mkdtemp()
        real = grok_store._read_text
        try:
            store = os.path.join(root, "sand-client-persistence")
            _blob(store, "sand.client.slice.account.a.roster.last-roster",
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"}]}}')
            moya = _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                         '{"schemaVersion":1,"value":{"entries":['
                         '{"kind":"send-message","id":"old","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"old reply"}}'
                         ']}}')
            grok_store._json_cache.clear()
            grok_store._read_problems.clear()
            _lines, _names, keys, active = grok_store.reply_snapshot(store)
            seen = set()
            grok_store.mark_seen(seen, keys)
            real_stat = os.stat

            def stat(path, *args, **kwargs):
                # Listed, then replaced: the name is gone by the time we stat it.
                # The reader stats the \\?\ form on Windows, so compare names.
                if os.path.basename(path) == os.path.basename(moya):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    raise FileNotFoundError(path)
                return real_stat(path, *args, **kwargs)

            os.stat = stat
            watched, _names, _keys, _path, _skipped = grok_store.watch_snapshot(
                store, seen=seen, follow_path=active)
            self.assertEqual(watched, [])
            self.assertTrue(any("FileNotFoundError" in text for text in grok_store._read_problems.values()))
            os.stat = real_stat
            replacement = moya + ".tmp"
            with open(replacement, "w", encoding="utf-8") as handle:
                handle.write('{"schemaVersion":1,"value":{"entries":['
                             '{"kind":"send-message","id":"old","seq":1,"timestampMs":1700000000000,"message":{"type":"text","content":"old reply"}},'
                             '{"kind":"send-message","id":"new","seq":2,"timestampMs":1700000005000,"message":{"type":"text","content":"just arrived"}}'
                             ']}}')
            os.replace(replacement, moya)
            watched, _names, keys, path, _skipped = grok_store.watch_snapshot(
                store, seen=seen, follow_path=active)
            fresh = grok_store.unseen_lines(seen, watched, keys)
            self.assertTrue(any("just arrived" in line for line in fresh))
            self.assertEqual(path, moya)
            self.assertEqual(grok_store.watch_heartbeat(70, None), "watching: 70 files, last change none")
            files, newest = grok_store.last_scan()
            self.assertGreaterEqual(files, 1)
            self.assertIsNotNone(newest)
            self.assertIn("last change", grok_store.watch_heartbeat(files, newest))
        finally:
            grok_store._read_text = real
            os.stat = real_stat
            grok_store._json_cache.clear()
            grok_store._read_problems.clear()
            shutil.rmtree(root)

    def test_windows_extended_prefix_is_drive_or_unc(self):
        self.assertEqual(grok_store._windows_long_path("C:\\foo\\bar"), "\\\\?\\C:\\foo\\bar")
        self.assertEqual(grok_store._windows_long_path("\\\\server\\share\\a"), "\\\\?\\UNC\\server\\share\\a")
        prefixed = "\\\\?\\C:\\foo\\bar"
        self.assertEqual(grok_store._windows_long_path(prefixed), prefixed)
        self.assertEqual(grok_store.extended_path(prefixed) if os.name == "nt" else prefixed, prefixed)
        if os.name == "nt":
            self.assertTrue(grok_store.extended_path("C:\\foo\\bar").startswith("\\\\?\\"))
            self.assertTrue(grok_store.extended_path("\\\\server\\share\\a").startswith("\\\\?\\UNC\\"))
        else:
            path = os.path.join(tempfile.gettempdir(), "grokbot-voice-short")
            self.assertEqual(grok_store.extended_path(path), path)
            self.assertEqual(grok_store.extended_path("out.wav"), "out.wav")

    def test_a_blob_past_max_path_is_read(self):
        """A chat file whose full path is longer than 260 characters is still read."""
        root = tempfile.mkdtemp()
        grok_store._json_cache.clear()
        grok_store._read_problems.clear()
        try:
            directory = root
            filename = grok_store.encode_base32(
                "sand.client.slice.account.a.transcript.replicas.moya") + ".blob"
            while len(os.path.abspath(os.path.join(directory, "sand-client-persistence", filename))) <= 260:
                directory = os.path.join(directory, "d" * 40)
            store = os.path.join(directory, "sand-client-persistence")
            os.makedirs(grok_store.extended_path(store), exist_ok=True)
            path = os.path.join(store, filename)
            self.assertGreater(len(os.path.abspath(path)), 260)
            roster = os.path.join(store, grok_store.encode_base32(
                "sand.client.slice.account.a.roster.last-roster") + ".blob")
            with open(grok_store.extended_path(roster), "w", encoding="utf-8") as handle:
                handle.write('{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"}]}}')
            with open(grok_store.extended_path(path), "w", encoding="utf-8") as handle:
                handle.write('{"schemaVersion":1,"value":{"entries":['
                             '{"kind":"send-message","id":"long","seq":1,"timestampMs":1700000000000,'
                             '"message":{"type":"text","content":"long path reply"}}]}}')
            lines, names = grok_store.reply_lines(store)
            self.assertTrue(any("long path reply" in line for line in lines), lines)
            self.assertIn("Moya", names)
            self.assertEqual(grok_store._read_problems, {})
            _lines, _names, keys, active = grok_store.reply_snapshot(store)
            seen = set()
            grok_store.mark_seen(seen, keys)
            with open(grok_store.extended_path(path), "w", encoding="utf-8") as handle:
                handle.write('{"schemaVersion":1,"value":{"entries":['
                             '{"kind":"send-message","id":"long","seq":1,"timestampMs":1700000000000,'
                             '"message":{"type":"text","content":"long path reply"}},'
                             '{"kind":"send-message","id":"next","seq":2,"timestampMs":1700000005000,'
                             '"message":{"type":"text","content":"spoken from a long path"}}]}}')
            watched, _names, keys, followed, skipped = grok_store.watch_snapshot(
                store, seen=seen, follow_path=active)
            fresh = grok_store.unseen_lines(seen, watched, keys)
            self.assertTrue(any("spoken from a long path" in line for line in fresh), fresh)
            self.assertEqual(followed, path)
            self.assertEqual(skipped, [])
            self.assertEqual(grok_store._read_problems, {})
        finally:
            grok_store._json_cache.clear()
            grok_store._read_problems.clear()
            shutil.rmtree(root)

    def test_unchanged_chat_file_is_not_read_twice(self):
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            path = _blob(store, "sand.client.slice.account.a.roster.last-roster",
                         '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"}]}}')
            grok_store._json_cache.clear()
            calls = {"n": 0}
            real = grok_store._read_text

            def counting(blob):
                calls["n"] += 1
                return real(blob)

            grok_store._read_text = counting
            try:
                self.assertEqual(grok_store._load_value(path)["rows"][0]["name"], "Moya")
                self.assertEqual(grok_store._load_value(path)["rows"][0]["name"], "Moya")
                self.assertEqual(calls["n"], 1)
            finally:
                grok_store._read_text = real
                grok_store._json_cache.clear()
        finally:
            shutil.rmtree(root)

    def test_xai_key_file_is_kept_when_the_keyring_is_empty(self):
        root = tempfile.mkdtemp()
        try:
            path = os.path.join(root, "xai-key")
            self.assertEqual(platform_linux.preserve_key_file(path, lambda: "secret-key"), "exported")
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "secret-key")
            self.assertEqual(platform_linux.preserve_key_file(path, lambda: "other"), "kept")
            self.assertEqual(platform_linux.preserve_key_file(os.path.join(root, "missing"), lambda: ""), "missing")
            self.assertEqual(platform_linux.preserve_key_file(os.path.join(root, "broken"), lambda: (_ for _ in ()).throw(OSError("no keyring"))), "missing")
        finally:
            shutil.rmtree(root)

    def test_back_forward_and_replay_follow_the_bot_on_screen(self):
        """Switching bots moves the history and the replay to that bot's latest reply."""
        root = tempfile.mkdtemp()
        try:
            store = os.path.join(root, "sand-client-persistence")
            roster = "sand.client.slice.account.a.roster.last-roster"
            selection = "sand.client.slice.account.a.ui.selected-agent"
            _blob(store, roster,
                  '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"},{"id":"cameron","name":"Cameron"}]}}')
            moya = _blob(store, "sand.client.slice.account.a.transcript.replicas.moya",
                         '{"schemaVersion":1,"value":{"entries":['
                         '{"kind":"send-message","id":"m1","seq":1,"timestampMs":1700000001000,"message":{"type":"text","content":"moya older"}},'
                         '{"kind":"send-message","id":"m2","seq":2,"timestampMs":1700000002000,"message":{"type":"text","content":"moya latest"}}'
                         ']}}')
            cameron = _blob(store, "sand.client.slice.account.a.transcript.replicas.cameron",
                            '{"schemaVersion":1,"value":{"entries":['
                            '{"kind":"send-message","id":"c1","seq":1,"timestampMs":1600000001000,"message":{"type":"text","content":"cameron older"}},'
                            '{"kind":"send-message","id":"c2","seq":2,"timestampMs":1600000002000,"message":{"type":"text","content":"cameron latest"}}'
                            ']}}')
            # Cameron's file is newer. That must not decide who is on screen.
            os.utime(cameron, (1_800_000_000, 1_800_000_000))
            os.utime(moya, (1_700_000_000, 1_700_000_000))

            def show(bot_id, title):
                _blob(store, selection,
                      '{"schemaVersion":1,"value":{"selectedAgentId":"%s"}}' % bot_id)
                lines, _names, keys, active = grok_store.reply_snapshot(
                    store, window_titles=[title])
                replay = grok_store.latest_replay(lines)
                return lines, keys, active, replay

            def check(bot_id, title, latest, other):
                lines, _keys, active, replay = show(bot_id, title)
                blob = grok_store.encode_base32(
                    "sand.client.slice.account.a.transcript.replicas." + bot_id) + ".blob"
                self.assertTrue(active.endswith(blob), active)
                self.assertTrue(all(bot_id == "moya" and line.startswith("Moya ") or
                                    bot_id == "cameron" and line.startswith("Cameron ")
                                    for line in lines), lines)
                self.assertEqual(len(lines), 2)
                self.assertIn(latest, replay)
                self.assertNotIn(other, replay)
                self.assertIn(latest, lines[-1])
                self.assertIn("window", grok_store.open_chat_line())
                # Forward walks the list to the newest. Back's first stop is that line.
                self.assertIn(latest, lines[-1])
                self.assertIn("older", lines[0])

            check("moya", "Moya — Grok Bot", "moya latest", "cameron")
            check("cameron", "Cameron — Grok Bot", "cameron latest", "moya")
            # The title is only "Grok Bot", so the saved selection is the bot on screen.
            # Cameron's latest reply is older and no new message has arrived.
            lines, _names, _keys, active = grok_store.reply_snapshot(
                store, window_titles=["Grok Bot"])
            self.assertIn("cameron latest", grok_store.latest_replay(lines))
            self.assertNotIn("moya", grok_store.latest_replay(lines))
            self.assertTrue(active.endswith(grok_store.encode_base32(
                "sand.client.slice.account.a.transcript.replicas.cameron") + ".blob"))
            self.assertIn("selection", grok_store.open_chat_line())
            check("moya", "Moya — Grok Bot", "moya latest", "cameron")

            # Startup already knows the viewed bot, so a reply in that chat is not skipped.
            seen = set()
            grok_store.mark_seen(seen, grok_store.every_reply_keylists(store))
            self._append_reply(
                moya,
                '{"schemaVersion":1,"value":{"entries":['
                '{"kind":"send-message","id":"m1","seq":1,"timestampMs":1700000001000,"message":{"type":"text","content":"moya older"}},'
                '{"kind":"send-message","id":"m2","seq":2,"timestampMs":1700000002000,"message":{"type":"text","content":"moya latest"}},'
                '{"kind":"send-message","id":"m3","seq":3,"timestampMs":1700000009000,"message":{"type":"text","content":"moya just arrived"}}'
                ']}}',
                1_700_000_050)
            _blob(store, selection, '{"schemaVersion":1,"value":{"selectedAgentId":"moya"}}')
            watched, _names, keys, path, skipped = grok_store.watch_snapshot(
                store, window_titles=["Moya — Grok Bot"], seen=seen, follow_path=None)
            fresh = grok_store.unseen_lines(seen, watched, keys)
            self.assertTrue(any("moya just arrived" in line for line in fresh), fresh)
            self.assertFalse(any("cameron" in line.lower() for line in fresh))
            self.assertNotIn("uncertain", grok_store.open_chat_line())
            self.assertTrue(path.endswith(grok_store.encode_base32(
                "sand.client.slice.account.a.transcript.replicas.moya") + ".blob"))
            self.assertTrue(all(reason == "not the open chat" for _k, reason, _line in skipped))
        finally:
            shutil.rmtree(root)

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
