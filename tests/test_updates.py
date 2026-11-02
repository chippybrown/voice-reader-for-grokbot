import json
import os
import shutil
import tempfile
import unittest

import updates


class Response:
    def __init__(self, data):
        self.data = data if isinstance(data, bytes) else data.encode("utf-8")

    def read(self, size=-1):
        if size is None or size < 0:
            data, self.data = self.data, b""
            return data
        data, self.data = self.data[:size], self.data[size:]
        return data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class UpdateTests(unittest.TestCase):
    def test_versions_and_the_two_messages(self):
        self.assertFalse(updates.newer("1.3.0", "v1.3.0"))
        self.assertTrue(updates.newer("1.3.0", "v1.3.1"))
        self.assertTrue(updates.newer("1.3.0", "v1.4.0"))
        self.assertTrue(updates.newer("1.2.9", "1.3.0"))
        self.assertFalse(updates.newer("1.10.0", "1.9.0"))
        current = updates.describe("1.3.0", {"tag_name": "v1.3.0", "assets": []})
        self.assertEqual(current["message"], "You're up to date (v1.3.0)")
        self.assertFalse(current["available"])
        ahead = updates.describe("1.3.0", {
            "tag_name": "v1.4.0",
            "assets": [
                {"name": "Grokbot-Voice-x86_64.AppImage", "browser_download_url": "https://example.test/app.AppImage"},
                {"name": "Grokbot.Voice.exe", "browser_download_url": "https://example.test/Grokbot.Voice.exe"},
                {"name": "grokbot-voice-linux-x86_64", "browser_download_url": "https://example.test/linux"},
            ],
        })
        self.assertEqual(ahead["message"], "v1.4.0 is available")
        self.assertTrue(ahead["available"])
        self.assertEqual(ahead["windows_name"], "Grokbot.Voice.exe")
        self.assertTrue(ahead["windows_url"].endswith(".exe"))
        patch = updates.describe("1.3.0", {
            "tag_name": "v1.3.1",
            "assets": [
                {"name": "Grokbot.Voice.exe", "browser_download_url": "https://example.test/Grokbot.Voice.exe"},
            ],
        })
        self.assertEqual(patch["message"], "v1.3.1 is available")
        self.assertTrue(patch["available"])
        self.assertTrue(patch["windows_url"].endswith("Grokbot.Voice.exe"))
        self.assertEqual(updates.describe("1.3.1", {"tag_name": "v1.3.1", "assets": []})["message"],
                         "You're up to date (v1.3.1)")

    def test_quiet_check_is_at_most_once_a_day(self):
        self.assertEqual(updates.launch_note("1.3.0", {}, 100), ("fetch", ""))
        waiting = {"checked": 1_000, "latest": "1.4.0", "available": True}
        self.assertEqual(updates.launch_note("1.3.0", waiting, 1_000 + 60), ("skip", "Update available"))
        self.assertEqual(updates.launch_note("1.4.0", waiting, 1_000 + 60), ("skip", ""))
        self.assertEqual(updates.launch_note("1.3.0", waiting, 1_000 + updates.DAY), ("fetch", ""))
        directory = tempfile.mkdtemp()
        try:
            path = os.path.join(directory, "update-check.json")
            updates.write_state(path, 50, {"latest": "1.4.0", "available": True})
            self.assertEqual(updates.read_state(path)["latest"], "1.4.0")
            self.assertTrue(updates.read_state(path)["available"])
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_linux_update_reruns_main_installer_without_apt_when_tools_exist(self):
        directory = tempfile.mkdtemp()
        calls = []

        def urlopen(_request, timeout=None):
            self.assertGreater(timeout, 0)
            return Response("#!/usr/bin/env bash\n# mint installer\necho install from main\n")

        def popen(args, **kwargs):
            calls.append((args, kwargs))
            return None

        try:
            helper = updates.apply(
                {"windows_url": ""}, "linux", 4321, "/usr/bin/python3", False, directory,
                urlopen, os.path.join(directory, "log.txt"),
                which=lambda name: "/usr/bin/" + name, popen=popen)
            with open(helper, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("kill -0 4321", text)
            self.assertIn("--no-apt", text)
            self.assertIn("install-mint.update.sh", text)
            self.assertIn("/main/install-mint.sh", updates.INSTALLER_URL)
            self.assertNotIn("cursor/linux-mint-port", updates.INSTALLER_URL)
            self.assertTrue(calls[0][1].get("start_new_session"))
            self.assertEqual(calls[0][0][0], "/bin/sh")
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_linux_update_allows_apt_when_python_is_missing(self):
        script = updates.linux_script(7, "/tmp/install-mint.update.sh", False, "/tmp/log.txt")
        self.assertNotIn("--no-apt", script)
        self.assertTrue(updates.needs_apt(lambda name: None if name == "python3" else "/usr/bin/git"))

    def test_windows_update_swaps_the_exe_after_exit(self):
        directory = tempfile.mkdtemp()
        calls = []

        def urlopen(_request, timeout=None):
            return Response(b"MZ" + b"x" * 100000)

        def popen(args, **kwargs):
            calls.append((args, kwargs))
            return None

        try:
            script = updates.apply(
                {"windows_url": "https://example.test/Grokbot.Voice.exe"},
                "win32", 99, r"C:\Users\Chip\Desktop\Grokbot Voice.exe", True, directory,
                urlopen, os.path.join(directory, "log.txt"), popen=popen)
            with open(script, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn('PID eq 99', text)
            self.assertIn(r"Grokbot Voice.exe", text)
            self.assertIn("move /Y", text)
            self.assertNotIn("python.exe", text.lower())
            self.assertEqual(calls[0][0][0], "cmd")
            source = updates.windows_script(3, directory + os.sep + "new.exe", directory + os.sep + "new.exe")
            self.assertNotIn("move /Y", source)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_check_reads_the_latest_release(self):
        body = json.dumps({"tag_name": "v1.3.0", "assets": []})

        def urlopen(request, timeout=None):
            self.assertIn("releases/latest", request.full_url)
            self.assertEqual(request.get_header("User-agent"), "grokbot-voice")
            return Response(body)

        result = updates.check("1.2.0", urlopen)
        self.assertEqual(result["message"], "v1.3.0 is available")
