# Check the public GitHub release and install it when asked.
# The network and the process start are passed in so tests stay offline.
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile

import grok_store
import hidden_process
import windows_launcher

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
        with open(grok_store.extended_path(path), encoding="utf-8") as handle:
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
        os.makedirs(grok_store.extended_path(folder), exist_ok=True)
    payload = {
        "checked": float(when),
        "latest": str((result or {}).get("latest") or ""),
        "available": bool((result or {}).get("available")),
    }
    with open(grok_store.extended_path(path), "w", encoding="utf-8") as handle:
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
    return windows_launcher.root_dir(localappdata)


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


def _starter_targets(downloaded, destination, install_dir, extras=None):
    """Starter exe paths that may be replaced. Never the program inside app."""
    if not downloaded:
        return []
    targets = []
    seen = set()
    for path in [destination] + list(extras or []):
        if not path:
            continue
        if install_dir and windows_launcher.is_inside(path, install_dir):
            continue
        key = windows_launcher._norm(path)
        if not key or key in seen:
            continue
        if windows_launcher._norm(downloaded) == key:
            continue
        seen.add(key)
        targets.append(path)
    return targets


def windows_script(pid, downloaded, destination, staging="", install_dir="", start_exe="", starter_copies=None):
    """Hidden script: wait until this process is gone, then swap in the new app folder.

    The real program lives in ...\\Grokbot Voice\\app. The script renames that
    folder aside, renames the extracted copy into its place, and puts the
    previous folder back if the rename fails. It does not delete the
    Grokbot Voice folder, and it does not copy the starter over app\\Grokbot Voice.exe.

    A cmd loop that pipes tasklist into find opens a console titled find "pid"
    when the helper has no console of its own, and that loop never notices
    the app has exited. WScript asks Windows whether the pid is still there,
    stops after a short budget of tries, and does not open a window.
    """
    pid = int(pid)
    targets = _starter_targets(downloaded, destination, install_dir, starter_copies)
    same = not targets
    src = _vbs_string(downloaded)
    # 80 tries at a quarter second is 20 seconds, then the swap runs anyway.
    lines = [
        "Option Explicit",
        "Dim shell, fso, tries, copied, staging, appDir, backup",
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
        backup = install_dir + ".old"
        lines.extend([
            "staging = %s" % _vbs_string(staging),
            "appDir = %s" % _vbs_string(install_dir),
            "backup = %s" % _vbs_string(backup),
            "If fso.FolderExists(staging) Then",
            "  If fso.FolderExists(backup) Then fso.DeleteFolder backup, True",
            "  On Error Resume Next",
            "  If fso.FolderExists(appDir) Then fso.MoveFolder appDir, backup",
            "  Err.Clear",
            "  fso.MoveFolder staging, appDir",
            "  If Err.Number <> 0 Then",
            "    If fso.FolderExists(backup) And Not fso.FolderExists(appDir) Then",
            "      Err.Clear",
            "      fso.MoveFolder backup, appDir",
            "    End If",
            "  Else",
            "    If fso.FolderExists(backup) Then fso.DeleteFolder backup, True",
            "  End If",
            "  On Error GoTo 0",
            "End If",
        ])
    for target in targets:
        lines.append("copied = ReplaceExe(fso, %s, %s)" % (src, _vbs_string(target)))
    if not targets:
        lines.append("copied = True")
    if start_exe:
        lines.append("shell.Run %s, 1, False" % _vbs_string('"' + start_exe + '"'))
    else:
        launch = downloaded if same else destination
        lines.extend([
            "If copied Then",
            "  shell.Run %s, 1, False" % _vbs_string('"' + launch + '"'),
            "Else",
            "  shell.Run %s, 1, False" % _vbs_string('"' + (downloaded or launch) + '"'),
            "End If",
        ])
    lines.extend([
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
    if targets:
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
    windows = system == "win32"
    if windows:
        # A new process group. hidden_process adds CREATE_NO_WINDOW and SW_HIDE.
        # DETACHED_PROCESS is not used: it lets each console tool open a window.
        kwargs["creationflags"] = 0x00000200
    else:
        kwargs["start_new_session"] = True
    launch = popen or hidden_process.popen
    if launch is not hidden_process.popen:
        kwargs = hidden_process.hidden_kwargs(kwargs, windows=windows)
    return launch(args, **kwargs)


def apply(result, system, pid, executable, frozen, directory, urlopen, log_path, which=None, popen=None):
    """Download the update and hand it to a helper. The caller then exits.

    Windows waits until this process quits, then renames the new program into
    %LOCALAPPDATA%\\Grokbot Voice\\app. The starter exe is updated only when
    it sits outside that folder. Linux re-runs the Mint installer from main,
    with --no-apt when git and Python are already installed, and that
    installer starts the app again.
    """
    which = which or shutil.which
    popen = popen or hidden_process.popen
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
        else:
            downloaded = ""
        running = executable if frozen and str(executable or "").lower().endswith(".exe") else ""
        staging = ""
        install = ""
        start = ""
        copies = []
        destination = running or downloaded
        if zip_url:
            zip_path = os.path.join(directory, "Grokbot-Voice-Windows.zip")
            _download(zip_url, zip_path, urlopen)
            with open(zip_path, "rb") as handle:
                if handle.read(2) != b"PK":
                    raise RuntimeError("Windows download was not the program")
            root = install_folder()
            os.makedirs(root, exist_ok=True)
            unpack = os.path.join(root, ".unpack-%s" % int(pid))
            if os.path.isdir(unpack):
                shutil.rmtree(unpack)
            os.makedirs(unpack)
            try:
                with zipfile.ZipFile(zip_path) as archive:
                    windows_launcher._safe_extract(archive, unpack)
                payload = windows_launcher.payload_dir(unpack)
                staging = os.path.join(root, ".app-new")
                if os.path.isdir(staging):
                    shutil.rmtree(staging)
                os.rename(payload, staging)
            finally:
                if os.path.isdir(unpack):
                    shutil.rmtree(unpack, ignore_errors=True)
            if not windows_launcher.is_program_dir(staging):
                raise RuntimeError("Windows download was not the program")
            install = windows_launcher.app_dir()
            start = os.path.join(install, windows_launcher.EXE_NAME)
            # Refresh a starter that sits beside app. Never the exe inside app,
            # including a 1.3.2 one-file exe that lived in the parent folder.
            for name in ("Grokbot.Voice.exe", "Grokbot Voice.exe"):
                candidate = os.path.join(root, name)
                if os.path.isfile(candidate):
                    copies.append(candidate)
            if running and not windows_launcher.is_inside(running, install):
                copies.append(running)
            destination = copies[0] if copies else downloaded
        script = os.path.join(directory, "update-run.vbs")
        try:
            os.remove(os.path.join(directory, "update-run.cmd"))
        except OSError:
            pass
        with open(script, "w", encoding="utf-8", newline="") as handle:
            handle.write(windows_script(pid, downloaded, destination, staging, install, start, copies))
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
