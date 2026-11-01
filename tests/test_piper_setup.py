import io
import os
import tempfile
import unittest
import zipfile

import piper_setup


class BytesResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False


class PiperSetupTests(unittest.TestCase):
    def test_catalog_has_female_and_male_voices(self):
        labels = [piper_setup.voice_label(path) for path in piper_setup.VOICE_PATHS]
        for name in ("Jenny", "Amy", "Lessac", "Alba", "Cori", "LJ Speech", "Ryan", "Alan", "Joe"):
            self.assertIn(name, labels)
        self.assertEqual(piper_setup.preferred_index(["David", "Jenny (natural)", "Amy (natural)"], ""), 1)
        self.assertEqual(piper_setup.preferred_index(["David", "Jenny (natural)"], "David"), 0)

    def test_missing_skips_files_already_there(self):
        root = tempfile.mkdtemp()
        try:
            folder = os.path.join(root, "piper")
            os.makedirs(folder)
            for name, body in (("piper.exe", b"exe"), ("en_US-amy-medium.onnx", b"onnx"), ("en_US-amy-medium.onnx.json", b"{}")):
                with open(os.path.join(folder, name), "wb") as handle:
                    handle.write(body)
            needed = piper_setup.missing_items(folder, "win32", "amd64")
            labels = [item[0] for item in needed]
            self.assertNotIn("Piper", labels)
            self.assertNotIn("Amy", labels)
            self.assertIn("Jenny", labels)
        finally:
            import shutil
            shutil.rmtree(root)

    def test_ensure_downloads_and_retries_then_stops_when_offline(self):
        root = tempfile.mkdtemp()
        try:
            folder = os.path.join(root, "piper")
            blob = io.BytesIO()
            with zipfile.ZipFile(blob, "w") as archive:
                archive.writestr("piper/piper.exe", b"piper-binary")
            archive_bytes = blob.getvalue()
            calls = {"n": 0}

            def urlopen(request, timeout=None):
                calls["n"] += 1
                url = request.full_url
                if url.endswith(".zip"):
                    if calls["n"] == 1:
                        raise OSError("offline")
                    return BytesResponse(archive_bytes)
                if "jenny" in url:
                    raise OSError("still offline")
                return BytesResponse(b"voice-bytes")

            messages = []
            ok = piper_setup.ensure(folder, "win32", messages.append, machine="amd64", urlopen=urlopen)
            self.assertFalse(ok)
            self.assertTrue(os.path.isfile(os.path.join(folder, "piper.exe")))
            self.assertTrue(any(msg.startswith("Downloading Piper") for msg in messages))
            self.assertTrue(messages[-1].startswith("Piper voices unavailable"))
            # The binary failure was retried, then a voice failed and we stopped.
            self.assertGreaterEqual(calls["n"], 2)
        finally:
            import shutil
            shutil.rmtree(root)
