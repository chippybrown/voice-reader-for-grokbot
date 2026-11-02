# Small Windows starter. Double-click this once; it installs the real program
# under LocalAppData and opens that copy afterwards.
#
# A one-file build of the whole app unpacked about 140 MB into %TEMP% on every
# launch, and Defender scanned it all. This file stays small. The speech
# program is unpacked once.
import os
import sys
import zipfile
import subprocess
import urllib.request

ZIP_NAME = "Grokbot-Voice-Windows.zip"
ZIP_URL = "https://github.com/chippybrown/voice-reader-for-grokbot/releases/latest/download/" + ZIP_NAME


def install_dir():
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, "Grokbot Voice")


def wanted_version():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(base, "version.txt"), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def installed_version(folder):
    try:
        with open(os.path.join(folder, "version.txt"), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def should_install(installed, wanted):
    """True when LocalAppData does not already hold this version."""
    return not wanted or installed != wanted


def _safe_extract(archive, folder):
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            raise RuntimeError("bad archive")
    archive.extractall(folder)


def install_zip(zip_path, folder):
    os.makedirs(folder, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        _safe_extract(archive, folder)


def fetch_zip(dest):
    partial = dest + ".partial"
    request = urllib.request.Request(ZIP_URL, headers={"User-Agent": "grokbot-voice"})
    with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as handle:
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    os.replace(partial, dest)


def main():
    folder = install_dir()
    wanted = wanted_version()
    if not should_install(installed_version(folder), wanted):
        subprocess.Popen([os.path.join(folder, "Grokbot Voice.exe")], cwd=folder, close_fds=True)
        return 0
    here = os.path.dirname(os.path.abspath(sys.argv[0]))
    sibling = os.path.join(here, ZIP_NAME)
    if not os.path.isfile(sibling):
        os.makedirs(folder, exist_ok=True)
        sibling = os.path.join(folder, ZIP_NAME)
        fetch_zip(sibling)
    install_zip(sibling, folder)
    subprocess.Popen([os.path.join(folder, "Grokbot Voice.exe")], cwd=folder, close_fds=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write("Grokbot Voice could not start: %s\n" % exc)
        raise SystemExit(1)
