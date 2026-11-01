# Check the public GitHub release and install it when asked.
# The network and the process start are passed in so tests stay offline.
import json
import os
import shutil
import subprocess
import urllib.request

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


def windows_asset(assets):
    """The Windows program. GitHub stores the spaced name as Grokbot.Voice.exe."""
    found = []
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if url and name.lower().endswith(".exe"):
            found.append((name, url))
    for name, url in found:
        if "voice" in name.lower():
            return name, url
    if found:
        return found[0]
    return "", ""


def describe(current, payload):
    """Turn the latest-release JSON into the two sentences Settings shows."""
    failed = {"ok": False, "available": False, "message": "Could not check for updates.",
              "latest": "", "windows_url": "", "windows_name": ""}
    if not isinstance(payload, dict):
        return failed
    tag = str(payload.get("tag_name") or "").strip()
    if not parse_version(tag):
        return failed
    name, url = windows_asset(payload.get("assets") or [])
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
        return "skip", ""
    return "fetch", ""


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


def _cmd_quote(path):
    return '"' + str(path).replace('"', '""') + '"'


def windows_script(pid, downloaded, destination):
    """Wait until this process is gone, then replace the exe and start it. No admin."""
    pid = int(pid)
    lines = [
        "@echo off",
        ":wait",
        'tasklist /FI "PID eq %d" 2>nul | find "%d" >nul' % (pid, pid),
        "if not errorlevel 1 (",
        "  ping -n 2 127.0.0.1 >nul",
        "  goto wait",
        ")",
    ]
    same = os.path.normcase(os.path.abspath(downloaded)) == os.path.normcase(os.path.abspath(destination))
    src = _cmd_quote(downloaded)
    dst = _cmd_quote(destination)
    if same:
        lines.append("start \"\" %s" % src)
    else:
        lines.append("move /Y %s %s" % (src, dst))
        lines.append("if errorlevel 1 (")
        lines.append("  start \"\" %s" % src)
        lines.append(") else (")
        lines.append("  start \"\" %s" % dst)
        lines.append(")")
    lines.append('del "%~f0"')
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
        # Detach so the helper keeps running after this program exits.
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
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
        url = str((result or {}).get("windows_url") or "")
        if not url:
            raise RuntimeError("no Windows download on that release")
        downloaded = os.path.join(directory, "GrokbotVoice-update.exe")
        _download(url, downloaded, urlopen)
        with open(downloaded, "rb") as handle:
            magic = handle.read(2)
        if magic != b"MZ" or os.path.getsize(downloaded) < 100000:
            raise RuntimeError("Windows download was not the program")
        if frozen and str(executable or "").lower().endswith(".exe"):
            destination = executable
        else:
            destination = downloaded
        script = os.path.join(directory, "update-run.cmd")
        with open(script, "w", encoding="utf-8", newline="") as handle:
            handle.write(windows_script(pid, downloaded, destination))
        _spawn(popen, ["cmd", "/c", script], "win32")
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
