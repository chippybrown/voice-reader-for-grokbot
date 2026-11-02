# Check the public GitHub release and install it when asked.
# The network and the process start are passed in so tests stay offline.
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile

REPO = "chippybrown/voice-reader-for-grokbot"
LATEST_URL = "https://api.github.com/repos/%s/releases/latest" % REPO
INSTALLER_URL = "https://raw.githubusercontent.com/chippybrown/voice-reader-for-grokbot/main/install-mint.sh"
DAY = 24 * 60 * 60
_AGENT = {"User-Agent": "grokbot-voice", "Accept": "application/vnd.github+json"}


def parse_version(text):
    """'v1.3.0' and '1.3.0' become (1, 3, 0). Anything else is None."""
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


def bare(text):
    raw = str(text or "").strip()
    if raw[:1] in ("v", "V"):
        raw = raw[1:]
    return raw


def newer(current, latest):
    """True when the release version is ahead of this copy."""
    here = parse_version(current)
    there = parse_version(latest)
    if not here or not there:
        return False
    width = max(len(here), len(there))
    here = here + (0,) * (width - len(here))
    there = there + (0,) * (width - len(there))
    return there > here


def windows_files(assets):
    """Launcher exe and the onedir zip. The exe name on GitHub uses a dot."""
    exe_name, exe_url = "", ""
    zip_name, zip_url = "", ""
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        lower = name.lower()
        if not url:
            continue
        if lower.endswith(".exe") and "voice" in lower and not exe_url:
            exe_name, exe_url = name, url
        elif lower.endswith(".zip") and "windows" in lower:
            zip_name, zip_url = name, url
    if not exe_url:
        for asset in assets or []:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            url = str(asset.get("browser_download_url") or "")
            if url and name.lower().endswith(".exe"):
                exe_name, exe_url = name, url
                break
    return exe_name, exe_url, zip_name, zip_url


def windows_asset(assets):
    """The Windows program. GitHub stores the spaced name as Grokbot.Voice.exe."""
    name, url, _zip_name, _zip_url = windows_files(assets)
    return name, url


def describe(current, payload):
    """Turn the latest-release JSON into the two sentences Settings shows."""
    failed = {"ok": False, "available": False, "message": "Could not check for updates.",
              "latest": "", "windows_url": "", "windows_name": ""}
    if not isinstance(payload, dict):
        return failed
    tag = str(payload.get("tag_name") or "").strip()
    if not parse_version(tag):
        return failed
    name, url, zip_name, zip_url = windows_files(payload.get("assets") or [])
    available = newer(current, tag)
    if available:
        message = "v%s is available" % bare(tag)
    else:
        message = "You're up to date (v%s)" % bare(current)
    return {
        "ok": True,
        "available": available,
        "message": message,
        "current": bare(current),
        "latest": bare(tag),
        "tag": tag,
        "windows_name": name,
        "windows_url": url,
        "zip_name": zip_name,
        "zip_url": zip_url,
    }


def fetch_latest(urlopen, timeout=20):
    request = urllib.request.Request(LATEST_URL, headers=_AGENT)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check(current, urlopen, timeout=20):
    return describe(current, fetch_latest(urlopen, timeout=timeout))


def read_state(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        checked = float(data.get("checked") or 0)
    except (TypeError, ValueError):
        checked = 0.0
    return {
        "checked": checked,
        "latest": str(data.get("latest") or ""),
        "available": bool(data.get("available")),
    }


def write_state(path, when, result):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = {
        "checked": float(when),
        "latest": str((result or {}).get("latest") or ""),
        "available": bool((result or {}).get("available")),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def due(checked, now, interval=DAY):
    try:
        last = float(checked or 0)
        moment = float(now)
    except (TypeError, ValueError):
        return True
    if last <= 0:
        return True
    return (moment - last) >= float(interval)


def launch_note(current, state, now):
    """Once a day, ask the network. Between checks, keep a known update on screen.

    Returns ('fetch', '') or ('skip', note). The note is empty when nothing new is waiting.
    """
    state = state or {}
    if not due(state.get("checked"), now):
        if state.get("available") and newer(current, state.get("latest")):
            return "skip", "Update available"
        if state.get("available"):
            return "clear", ""
        return "skip", ""
    return "fetch", ""


def remove_old_updater(directory):
    """Delete the 1.3.1 cmd loop and its downloaded exe, if a failed update left them."""
    if not directory:
        return
    for name in ("update-run.cmd", "GrokbotVoice-update.exe"):
        try:
            os.remove(os.path.join(directory, name))
        except OSError:
            pass


def install_folder(localappdata=None):
    root = localappdata or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(root, "Grokbot Voice")


def _download(url, dest, urlopen, timeout=120):
    request = urllib.request.Request(url, headers={"User-Agent": "grokbot-voice"})
    partial = dest + ".partial"
    with urlopen(request, timeout=timeout) as response, open(partial, "wb") as handle:
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    os.replace(partial, dest)


def _vbs_string(text):
    return '"' + str(text).replace('"', '""') + '"'


def windows_script(pid, downloaded, destination, staging="", install_dir="", start_exe=""):
    """Hidden script: wait until this process is gone, then replace the exe and start it.

    A cmd loop that pipes tasklist into find opens a console titled find "pid"
    when the helper has no console of its own, and that loop never notices
    the app has exited. WScript asks Windows whether the pid is still there,
    stops after a short budget of tries, and does not open a window.
    """
    pid = int(pid)
    same = os.path.normcase(os.path.abspath(downloaded)) == os.path.normcase(os.path.abspath(destination))
    src = _vbs_string(downloaded)
    dst = _vbs_string(destination)
    # 80 tries at a quarter second is 20 seconds, then the swap runs anyway.
    lines = [
        "Option Explicit",
        "Dim shell, fso, tries, copied",
        "Set shell = CreateObject(\"WScript.Shell\")",
        "Set fso = CreateObject(\"Scripting.FileSystemObject\")",
        "tries = 0",
        "Do",
        "  tries = tries + 1",
        "  If tries > 80 Then Exit Do",
        "  If Not ProcessRunning(%d) Then Exit Do" % pid,
        "  WScript.Sleep 250",
        "Loop",
    ]
    if staging and install_dir:
        lines.extend([
            "If fso.FolderExists(%s) Then" % _vbs_string(staging),
            "  If fso.FolderExists(%s) Then fso.DeleteFolder %s, True" % (_vbs_string(install_dir), _vbs_string(install_dir)),
            "  fso.CopyFolder %s, %s" % (_vbs_string(staging), _vbs_string(install_dir)),
            "End If",
        ])
    lines.append("copied = %s" % ("True" if same else "False"))
    if not same:
        lines.extend([
            "If Not copied Then",
            "  copied = ReplaceExe(fso, %s, %s)" % (src, dst),
            "End If",
        ])
    launch = start_exe or (downloaded if same else destination)
    lines.extend([
        "If copied Then",
        "  shell.Run %s, 1, False" % _vbs_string('"' + launch + '"'),
        "Else",
        "  shell.Run %s, 1, False" % _vbs_string('"' + (start_exe or downloaded) + '"'),
        "End If",
        "On Error Resume Next",
        "fso.DeleteFile WScript.ScriptFullName, True",
        "",
        "Function ProcessRunning(pid)",
        "  On Error Resume Next",
        "  Dim items",
        "  Set items = GetObject(\"winmgmts:\\\\.\\root\\cimv2\").ExecQuery(\"SELECT ProcessId FROM Win32_Process WHERE ProcessId = \" & CLng(pid))",
        "  If Err.Number <> 0 Then",
        "    ProcessRunning = False",
        "  Else",
        "    ProcessRunning = (items.Count > 0)",
        "  End If",
        "End Function",
        "",
    ])
    if not same:
        lines.extend([
            "Function ReplaceExe(fso, src, dst)",
            "  Dim attempt",
            "  ReplaceExe = False",
            "  For attempt = 1 To 10",
            "    On Error Resume Next",
            "    Err.Clear",
            "    fso.CopyFile src, dst, True",
            "    If Err.Number = 0 Then",
            "      ReplaceExe = True",
            "      Exit Function",
            "    End If",
            "    WScript.Sleep 400",
            "  Next",
            "End Function",
            "",
        ])
    return "\r\n".join(lines) + "\r\n"


def _sh_quote(text):
    return "'" + str(text).replace("'", "'\"'\"'") + "'"


def needs_apt(which):
    """The Mint installer can skip apt when git and Python are already here."""
    return not (which("git") and which("python3"))


def linux_script(pid, installer, no_apt, log_path):
    pid = int(pid)
    flag = " --no-apt" if no_apt else ""
    lines = [
        "#!/bin/sh",
        "while kill -0 %d 2>/dev/null; do" % pid,
        "  sleep 0.3",
        "done",
        "export GROKBOT_VOICE_AUTOSTART=0",
        "bash %s%s >> %s 2>&1" % (_sh_quote(installer), flag, _sh_quote(log_path)),
        "",
    ]
    return "\n".join(lines)


def _spawn(popen, args, system):
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if system == "win32":
        # CREATE_NO_WINDOW, and not DETACHED_PROCESS. Detached drops the
        # console flag and each console tool then opens a window of its own.
        kwargs["creationflags"] = 0x00000200 | 0x08000000
    else:
        kwargs["start_new_session"] = True
    return popen(args, **kwargs)


def apply(result, system, pid, executable, frozen, directory, urlopen, log_path, which=None, popen=None):
    """Download the update and hand it to a helper. The caller then exits.

    Windows replaces the running exe after it quits. Linux re-runs the Mint
    installer from main, with --no-apt when git and Python are already installed,
    and that installer starts the app again.
    """
    which = which or shutil.which
    popen = popen or subprocess.Popen
    os.makedirs(directory, exist_ok=True)
    if system == "win32":
        exe_url = str((result or {}).get("windows_url") or "")
        zip_url = str((result or {}).get("zip_url") or "")
        if not exe_url and not zip_url:
            raise RuntimeError("no Windows download on that release")
        downloaded = os.path.join(directory, "GrokbotVoice-update.exe")
        if exe_url:
            _download(exe_url, downloaded, urlopen)
            with open(downloaded, "rb") as handle:
                magic = handle.read(2)
            if magic != b"MZ" or os.path.getsize(downloaded) < 100000:
                raise RuntimeError("Windows download was not the program")
        running = executable if frozen and str(executable or "").lower().endswith(".exe") else ""
        onedir = bool(running) and os.path.isdir(os.path.join(os.path.dirname(running), "_internal"))
        staging = ""
        install = ""
        start = ""
        if zip_url:
            zip_path = os.path.join(directory, "Grokbot-Voice-Windows.zip")
            _download(zip_url, zip_path, urlopen)
            with open(zip_path, "rb") as handle:
                if handle.read(2) != b"PK":
                    raise RuntimeError("Windows download was not the program")
            staging = os.path.join(directory, "update-staging")
            if os.path.isdir(staging):
                shutil.rmtree(staging)
            os.makedirs(staging)
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(staging)
            install = os.path.dirname(running) if onedir else install_folder()
            start = os.path.join(install, "Grokbot Voice.exe")
        if onedir:
            downloaded = start or downloaded
            destination = start or downloaded
        elif running:
            destination = running
        else:
            destination = downloaded
        script = os.path.join(directory, "update-run.vbs")
        try:
            os.remove(os.path.join(directory, "update-run.cmd"))
        except OSError:
            pass
        with open(script, "w", encoding="utf-8", newline="") as handle:
            handle.write(windows_script(pid, downloaded, destination, staging, install, start))
        root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
        wscript = os.path.join(root, "System32", "wscript.exe") if root else "wscript.exe"
        # //B is batch mode: no script errors and no console window.
        _spawn(popen, [wscript, "//B", "//Nologo", script], "win32")
        return script
    installer = os.path.join(directory, "install-mint.update.sh")
    _download(INSTALLER_URL, installer, urlopen, timeout=60)
    with open(installer, "rb") as handle:
        head = handle.read(2)
    if head != b"#!" or os.path.getsize(installer) < 50:
        raise RuntimeError("installer download was not the Mint script")
    os.chmod(installer, 0o755)
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    helper = os.path.join(directory, "update-run.sh")
    no_apt = not needs_apt(which)
    with open(helper, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(linux_script(pid, installer, no_apt, log_path))
    os.chmod(helper, 0o755)
    _spawn(popen, ["/bin/sh", helper], system)
    return helper
