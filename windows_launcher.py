# Small Windows starter. Double-click this once; it installs the real program
# under LocalAppData\Grokbot Voice\app and opens that copy afterwards.
#
# The starter is a one-file program. It unpacks itself into %TEMP%\_MEI*
# and deletes that folder when it exits. The real program must not be
# unpacked into the starter's own folder: a _internal directory beside the
# starter, or a child process that inherits _MEIPASS2, makes Windows look
# for python312.dll in a folder that is already gone.
import os
import shutil
import subprocess
import sys
import time
import zipfile
import urllib.request

import hidden_process

ZIP_NAME = "Grokbot-Voice-Windows.zip"
ZIP_URL = "https://github.com/chippybrown/voice-reader-for-grokbot/releases/latest/download/" + ZIP_NAME
EXE_NAME = "Grokbot Voice.exe"
# PyInstaller tells a child process to reuse the parent's temp extract.
_INHERITED = ("_MEIPASS", "_MEIPASS2", "_PYI_APPLICATION_HOME_DIR", "_PYI_PARENT_PROCESS_LEVEL", "_PYI_ARCHIVE_FILE")


def root_dir(localappdata=None):
    root = localappdata or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, "Grokbot Voice")


def app_dir(localappdata=None):
    """The real program. Never the folder that holds the running starter."""
    return os.path.join(root_dir(localappdata), "app")


def _norm(path):
    text = str(path or "").replace("/", "\\")
    while "\\\\" in text:
        text = text.replace("\\\\", "\\")
    return text.rstrip("\\").lower()


def is_inside(path, folder):
    """True when path is folder or a file inside it. Slashes do not matter."""
    path = _norm(path)
    folder = _norm(folder)
    if not path or not folder:
        return False
    return path == folder or path.startswith(folder + "\\")


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


def _parse_version(text):
    raw = str(text or "").strip()
    if raw[:1] in ("v", "V"):
        raw = raw[1:]
    if not raw:
        return None
    parts = []
    for piece in raw.split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            return None
        parts.append(int(digits))
    return tuple(parts)


def should_install(installed, wanted):
    """True when the copy in app is missing or older than this starter.

    A newer app is left alone, so an old starter cannot install an older zip
    over it.
    """
    if not wanted:
        return not installed
    if not installed:
        return True
    have = _parse_version(installed)
    need = _parse_version(wanted)
    if not have or not need:
        return installed != wanted
    width = max(len(have), len(need))
    have = have + (0,) * (width - len(have))
    need = need + (0,) * (width - len(need))
    return need > have


def is_program_dir(folder):
    return os.path.isfile(os.path.join(folder, EXE_NAME)) and os.path.isdir(os.path.join(folder, "_internal"))


def payload_dir(folder):
    """Directory inside an extracted zip that holds Grokbot Voice.exe and _internal.

    The zip may be the program itself, or the program inside an app folder
    with the starter exe sitting beside that folder.
    """
    nested = os.path.join(folder, "app")
    if is_program_dir(nested):
        return nested
    if is_program_dir(folder):
        return folder
    raise RuntimeError("archive is missing the program")


def _safe_extract(archive, folder):
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            raise RuntimeError("bad archive")
    archive.extractall(folder)


def _replace_tree(payload, dest):
    """Rename payload onto dest. The previous dest is restored if the rename fails."""
    if _norm(payload) == _norm(dest):
        return
    parent = os.path.dirname(dest)
    os.makedirs(parent, exist_ok=True)
    backup = os.path.join(parent, ".app-old-%s" % os.getpid())
    if os.path.isdir(backup):
        shutil.rmtree(backup)
    moved_old = False
    try:
        if os.path.isdir(dest):
            os.rename(dest, backup)
            moved_old = True
        os.rename(payload, dest)
    except Exception:
        if moved_old and not os.path.isdir(dest) and os.path.isdir(backup):
            os.rename(backup, dest)
        raise
    if os.path.isdir(backup):
        shutil.rmtree(backup, ignore_errors=True)


def install_zip(zip_path, folder):
    """Extract to a temp folder beside folder, then rename it into place.

    folder is ...\\Grokbot Voice\\app. The running starter stays outside it.
    """
    starter = os.path.abspath(sys.argv[0])
    if is_inside(starter, folder):
        raise RuntimeError("refusing to install over the running starter")
    parent = os.path.dirname(folder)
    os.makedirs(parent, exist_ok=True)
    unpack = os.path.join(parent, ".unpack-%s" % os.getpid())
    if os.path.isdir(unpack):
        shutil.rmtree(unpack)
    os.makedirs(unpack)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            _safe_extract(archive, unpack)
        payload = payload_dir(unpack)
        _replace_tree(payload, folder)
    finally:
        if os.path.isdir(unpack):
            shutil.rmtree(unpack, ignore_errors=True)
    if not is_program_dir(folder):
        raise RuntimeError("install did not produce the program")


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


def directory_in_use(path):
    """True when a running program still has this folder open.

    Windows refuses to rename a directory while a DLL inside it is loaded.
    """
    probe = path + ".inuse"
    try:
        os.rename(path, probe)
    except OSError:
        return True
    try:
        os.rename(probe, path)
    except OSError:
        return True
    return False


def clean_old_mei(temp=None, in_use=None, current=None):
    """Delete leftover _MEI folders from older one-file runs. Skip any that are open."""
    temp = temp or os.environ.get("TEMP") or os.environ.get("TMP") or ""
    if not temp or not os.path.isdir(temp):
        return []
    in_use = in_use or directory_in_use
    if current is None:
        current = getattr(sys, "_MEIPASS", "") or ""
    current_norm = _norm(current)
    removed = []
    try:
        names = os.listdir(temp)
    except OSError:
        return removed
    for name in names:
        if not name.startswith("_MEI"):
            continue
        path = os.path.join(temp, name)
        if not os.path.isdir(path):
            continue
        if current_norm and _norm(path) == current_norm:
            continue
        try:
            busy = in_use(path)
        except OSError:
            busy = True
        if busy:
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.isdir(path):
            removed.append(path)
    return removed


def remove_stray_internal(starter_path, app_folder):
    """Delete a _internal folder left beside the starter by the 1.3.4 update."""
    folder = os.path.dirname(os.path.abspath(starter_path))
    if is_inside(folder, app_folder):
        return
    stray = os.path.join(folder, "_internal")
    if os.path.isdir(stray) and not is_inside(stray, app_folder):
        shutil.rmtree(stray, ignore_errors=True)


def launch_env(source=None):
    """Environment for the real program. It must not reuse the starter's temp extract."""
    env = dict(os.environ if source is None else source)
    for key in list(env):
        if key.upper() in _INHERITED or key.upper().startswith("_PYI_") or key.upper().startswith("_MEIPASS"):
            env.pop(key, None)
    return env


def spawn_program(exe, env=None, popen=None):
    launch = popen or hidden_process.popen
    folder = os.path.dirname(exe)
    # Valid NUL handles, not inherited nulls. A windowed child otherwise
    # starts with sys.stdout and sys.stderr set to None.
    kwargs = {
        "cwd": folder,
        "env": launch_env(env),
        "close_fds": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        # A new process group. The helper adds CREATE_NO_WINDOW and SW_HIDE.
        # DETACHED_PROCESS is not used: it lets each console tool open a window.
        kwargs["creationflags"] = 0x00000200
    return launch([exe], **kwargs)


def log_line(folder, message):
    try:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "starter-log.txt"), "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%H:%M:%S ") + str(message) + "\n")
    except OSError:
        pass


def _zip_path(root):
    here = os.path.dirname(os.path.abspath(sys.argv[0]))
    sibling = os.path.join(here, ZIP_NAME)
    if os.path.isfile(sibling):
        return sibling
    os.makedirs(root, exist_ok=True)
    downloaded = os.path.join(root, ZIP_NAME)
    if not os.path.isfile(downloaded):
        fetch_zip(downloaded)
    return downloaded


def main():
    root = root_dir()
    app = app_dir()
    os.makedirs(root, exist_ok=True)
    clean_old_mei()
    exe = os.path.join(app, EXE_NAME)
    wanted = wanted_version()
    if os.path.isfile(exe) and not should_install(installed_version(app), wanted):
        remove_stray_internal(sys.argv[0], app)
        log_line(root, "launch %s" % exe)
        spawn_program(exe)
        return 0
    zip_path = _zip_path(root)
    log_line(root, "install %s into %s" % (zip_path, app))
    install_zip(zip_path, app)
    remove_stray_internal(sys.argv[0], app)
    exe = os.path.join(app, EXE_NAME)
    log_line(root, "launch %s" % exe)
    spawn_program(exe)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        try:
            log_line(root_dir(), "could not start: %s" % exc)
        except Exception:
            pass
        sys.stderr.write("Grokbot Voice could not start: %s\n" % exc)
        raise SystemExit(1)
