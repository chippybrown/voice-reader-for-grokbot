# Fresh install, and an upgrade from the 1.3.2 one-file exe, without Windows.
import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

import updates
import windows_launcher


def _zip_bytes(version, nested=True, starter=b"MZ-starter"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        prefix = "app/" if nested else ""
        archive.writestr(prefix + "Grokbot Voice.exe", b"MZ-app-" + version.encode("ascii"))
        archive.writestr(prefix + "_internal/python312.dll", b"dll-" + version.encode("ascii"))
        archive.writestr(prefix + "version.txt", version)
        if nested:
            archive.writestr("Grokbot Voice.exe", starter)
    return buffer.getvalue()


def _write_zip(path, version, nested=True, starter=b"MZ-starter"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(_zip_bytes(version, nested=nested, starter=starter))


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


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.local = os.path.join(self.home, "local")
        self.temp = os.path.join(self.home, "temp")
        os.makedirs(self.local)
        os.makedirs(self.temp)
        self.env = {
            "LOCALAPPDATA": os.environ.get("LOCALAPPDATA"),
            "TEMP": os.environ.get("TEMP"),
            "TMP": os.environ.get("TMP"),
            "_MEIPASS": os.environ.get("_MEIPASS"),
            "_MEIPASS2": os.environ.get("_MEIPASS2"),
        }
        os.environ["LOCALAPPDATA"] = self.local
        os.environ["TEMP"] = self.temp
        os.environ["TMP"] = self.temp
        self.argv = sys.argv[:]
        self.had_meipass = hasattr(sys, "_MEIPASS")
        self.meipass = getattr(sys, "_MEIPASS", None)
        self.popen = windows_launcher.subprocess.Popen
        self.calls = []

        def popen(args, **kwargs):
            self.calls.append((args, kwargs))
            return None

        windows_launcher.subprocess.Popen = popen

    def tearDown(self):
        sys.argv = self.argv
        windows_launcher.subprocess.Popen = self.popen
        if self.had_meipass:
            sys._MEIPASS = self.meipass
        elif hasattr(sys, "_MEIPASS"):
            delattr(sys, "_MEIPASS")
        for key, value in self.env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.home, ignore_errors=True)

    def _starter(self, folder, name="Grokbot.Voice.exe", body=b"MZ-starter", version="1.3.5"):
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        with open(path, "wb") as handle:
            handle.write(body)
        meipass = os.path.join(self.home, "meipass")
        os.makedirs(meipass, exist_ok=True)
        with open(os.path.join(meipass, "version.txt"), "w", encoding="utf-8") as handle:
            handle.write(version)
        sys._MEIPASS = meipass
        sys.argv = [path]
        return path

    def test_fresh_install_puts_the_program_in_app_and_launches_it(self):
        starter_dir = os.path.join(self.home, "download")
        starter = self._starter(starter_dir)
        _write_zip(os.path.join(starter_dir, windows_launcher.ZIP_NAME), "1.3.5")
        os.environ["_MEIPASS2"] = os.path.join(self.temp, "_MEIparent")
        os.environ["_MEIPASS"] = os.environ["_MEIPASS2"]
        self.assertEqual(windows_launcher.main(), 0)
        app = windows_launcher.app_dir()
        with open(os.path.join(app, "Grokbot Voice.exe"), "rb") as handle:
            self.assertEqual(handle.read(), b"MZ-app-1.3.5")
        self.assertTrue(os.path.isfile(os.path.join(app, "_internal", "python312.dll")))
        self.assertFalse(os.path.isdir(os.path.join(starter_dir, "_internal")))
        self.assertFalse(os.path.isdir(os.path.join(windows_launcher.root_dir(), "_internal")))
        with open(starter, "rb") as handle:
            self.assertEqual(handle.read(), b"MZ-starter")
        self.assertEqual(self.calls[0][0], [os.path.join(app, "Grokbot Voice.exe")])
        self.assertEqual(self.calls[0][1]["cwd"], app)
        env = self.calls[0][1]["env"]
        self.assertNotIn("_MEIPASS2", env)
        self.assertNotIn("_MEIPASS", env)
        # A second start leaves the installed copy alone.
        with open(os.path.join(app, "keep.txt"), "w", encoding="utf-8") as handle:
            handle.write("stay")
        self.calls.clear()
        self.assertEqual(windows_launcher.main(), 0)
        with open(os.path.join(app, "keep.txt"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "stay")
        self.assertEqual(self.calls[0][0], [os.path.join(app, "Grokbot Voice.exe")])

    def test_upgrade_from_a_132_onefile_does_not_unpack_over_the_starter(self):
        root = windows_launcher.root_dir()
        os.makedirs(root, exist_ok=True)
        # 1.3.2's updater copies the new starter over the running one-file exe.
        starter = self._starter(root, name="Grokbot Voice.exe", body=b"MZ-starter-1.3.5")
        with open(os.path.join(root, "version-was.txt"), "w", encoding="utf-8") as handle:
            handle.write("1.3.2")
        _write_zip(os.path.join(root, windows_launcher.ZIP_NAME), "1.3.5", starter=b"MZ-starter-in-zip")
        self.assertEqual(windows_launcher.main(), 0)
        with open(starter, "rb") as handle:
            self.assertEqual(handle.read(), b"MZ-starter-1.3.5")
        self.assertFalse(os.path.isdir(os.path.join(root, "_internal")))
        app = windows_launcher.app_dir()
        self.assertTrue(os.path.isfile(os.path.join(app, "_internal", "python312.dll")))
        with open(os.path.join(app, "Grokbot Voice.exe"), "rb") as handle:
            self.assertTrue(handle.read().startswith(b"MZ-app-"))
        self.assertEqual(self.calls[0][0], [os.path.join(app, "Grokbot Voice.exe")])
        self.assertNotIn("_MEIPASS2", self.calls[0][1]["env"])
        self.assertTrue(os.path.isfile(os.path.join(root, "version-was.txt")))

    def test_stray_internal_beside_the_starter_is_removed(self):
        root = windows_launcher.root_dir()
        os.makedirs(os.path.join(root, "_internal"), exist_ok=True)
        with open(os.path.join(root, "_internal", "python312.dll"), "wb") as handle:
            handle.write(b"leftover")
        self._starter(root, name="Grokbot Voice.exe")
        _write_zip(os.path.join(root, windows_launcher.ZIP_NAME), "1.3.5")
        self.assertEqual(windows_launcher.main(), 0)
        self.assertFalse(os.path.isdir(os.path.join(root, "_internal")))
        self.assertTrue(os.path.isdir(os.path.join(windows_launcher.app_dir(), "_internal")))

    def test_a_bad_archive_leaves_the_installed_program(self):
        app = windows_launcher.app_dir()
        os.makedirs(os.path.join(app, "_internal"), exist_ok=True)
        with open(os.path.join(app, "Grokbot Voice.exe"), "wb") as handle:
            handle.write(b"MZ-old")
        with open(os.path.join(app, "version.txt"), "w", encoding="utf-8") as handle:
            handle.write("1.3.4")
        with open(os.path.join(app, "keep.txt"), "w", encoding="utf-8") as handle:
            handle.write("stay")
        bad = os.path.join(self.home, "bad.zip")
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("readme.txt", "not the program")
        sys.argv = [os.path.join(self.home, "Grokbot.Voice.exe")]
        with self.assertRaises(RuntimeError):
            windows_launcher.install_zip(bad, app)
        with open(os.path.join(app, "keep.txt"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "stay")
        self.assertFalse(any(name.startswith(".unpack-") or name.startswith(".app-old-")
                             for name in os.listdir(windows_launcher.root_dir())))
        self.assertFalse(windows_launcher.should_install("1.3.5", "1.3.4"))
        self.assertTrue(windows_launcher.should_install("1.3.4", "1.3.5"))

    def test_old_mei_folders_are_removed_unless_they_are_in_use(self):
        live = os.path.join(self.temp, "_MEIlive")
        old = os.path.join(self.temp, "_MEIold")
        busy = os.path.join(self.temp, "_MEIbusy")
        for path in (live, old, busy):
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, "python312.dll"), "wb") as handle:
                handle.write(b"dll")
        removed = windows_launcher.clean_old_mei(
            self.temp, in_use=lambda path: os.path.basename(path) == "_MEIbusy", current=live)
        self.assertTrue(os.path.isdir(live))
        self.assertTrue(os.path.isdir(busy))
        self.assertFalse(os.path.isdir(old))
        self.assertIn(old, removed)

    def test_updater_from_a_132_onefile_swaps_the_app_folder(self):
        root = windows_launcher.root_dir()
        os.makedirs(root, exist_ok=True)
        onefile = os.path.join(root, "Grokbot Voice.exe")
        with open(onefile, "wb") as handle:
            handle.write(b"MZ-old-1.3.2")
        directory = os.path.join(self.home, "config")
        os.makedirs(directory)
        package = _zip_bytes("1.3.5")
        calls = []

        def urlopen(request, timeout=None):
            url = request.full_url
            if url.endswith(".zip"):
                return Response(package)
            return Response(b"MZ" + b"s" * 100000)

        def popen(args, **kwargs):
            calls.append(args)
            return None

        script = updates.apply(
            {"windows_url": "https://example.test/Grokbot.Voice.exe",
             "zip_url": "https://example.test/Grokbot-Voice-Windows.zip"},
            "win32", 132, onefile, True, directory, urlopen,
            os.path.join(directory, "log.txt"), popen=popen)
        with open(script, encoding="utf-8") as handle:
            text = handle.read()
        staging = os.path.join(root, ".app-new")
        app = windows_launcher.app_dir()
        self.assertTrue(windows_launcher.is_program_dir(staging))
        self.assertFalse(os.path.isdir(os.path.join(staging, "app")))
        self.assertIn("MoveFolder", text)
        self.assertIn(".app-new", text)
        self.assertIn(os.path.join(app, "Grokbot Voice.exe"), text)
        self.assertNotIn("CopyFolder", text)
        self.assertNotIn('DeleteFolder "%s"' % root, text)
        # The starter may replace the old one-file exe. It must not replace the app exe.
        app_exe = os.path.join(app, "Grokbot Voice.exe")
        self.assertNotIn("ReplaceExe(fso, %s, %s)" % (updates._vbs_string(os.path.join(directory, "GrokbotVoice-update.exe")), updates._vbs_string(app_exe)), text)
        self.assertIn(updates._vbs_string(onefile), text)
        with open(onefile, "rb") as handle:
            self.assertEqual(handle.read(), b"MZ-old-1.3.2")
        self.assertIn("//B", calls[0])

    def test_release_zip_keeps_internal_inside_app(self):
        """A 1.3.3 updater copies the zip onto the install folder and runs Grokbot Voice.exe there.

        That exe has to be the starter, with _internal only inside app, or the
        starter boots beside the real program's DLLs and then loses them.
        """
        folder = os.path.join(self.home, "copied-by-old-updater")
        os.makedirs(folder)
        with zipfile.ZipFile(io.BytesIO(_zip_bytes("1.3.5", starter=b"MZ-starter"))) as archive:
            archive.extractall(folder)
        self.assertFalse(windows_launcher.is_program_dir(folder))
        self.assertTrue(windows_launcher.is_program_dir(os.path.join(folder, "app")))
        with open(os.path.join(folder, "Grokbot Voice.exe"), "rb") as handle:
            self.assertEqual(handle.read(), b"MZ-starter")
