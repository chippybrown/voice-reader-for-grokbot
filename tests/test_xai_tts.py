import io
import unittest
import wave

import xai_tts


class SpeechRequestTests(unittest.TestCase):
    def test_payload_matches_the_current_tts_api(self):
        body = xai_tts.payload('She said \u201cwait\u201d\u2026', "Carina", 4)
        self.assertEqual(body["text"], 'She said "wait"...')
        self.assertEqual(body["voice_id"], "Carina")
        self.assertEqual(body["language"], "en")
        self.assertEqual(body["speed"], 1.5)
        self.assertEqual(body["output_format"], {"codec": "wav", "sample_rate": 24000})
        self.assertNotIn("auto", body["language"])
        self.assertEqual(xai_tts.payload("Hello.", "not a voice!", 1)["voice_id"], "eve")
        long_words = xai_tts.spoken_text("word " * 40000)
        self.assertLessEqual(len(long_words), xai_tts.MAX_CHARS)
        self.assertFalse(long_words.endswith(" wor"))
        self.assertLessEqual(len(xai_tts.spoken_text("a" * 70000)), xai_tts.MAX_CHARS)
        with self.assertRaises(ValueError):
            xai_tts.payload("   ", "eve", 1)

    def test_error_log_includes_the_body_and_not_the_key(self):
        line = xai_tts.error_log(400, b'{"error":"bad codec"} Authorization: Bearer xai-secretkey')
        self.assertIn("HTTP 400", line)
        self.assertIn("bad codec", line)
        self.assertNotIn("xai-secretkey", line)
        self.assertNotIn("Bearer xai", line)

    def test_wav_and_json_envelopes_become_pcm(self):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24000)
            handle.writeframes(b"\x01\x00\x02\x00")
        wav = buffer.getvalue()
        self.assertEqual(xai_tts.pcm_bytes(wav, "audio/wav"), b"\x01\x00\x02\x00")
        import base64
        envelope = b'{"audio":"%s","content_type":"audio/wav"}' % base64.b64encode(wav)
        self.assertEqual(xai_tts.pcm_bytes(envelope, "application/json"), b"\x01\x00\x02\x00")
