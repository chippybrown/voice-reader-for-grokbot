# Linux pieces: chat files, paplay, the Secret Service keyring, Piper's binary, espeak-ng.
import os
import shutil
import signal
import subprocess
import sys
import threading

import grok_store
from audio_util import pitch_ratio, scale_wav_rate

KEYRING_SERVICE = "grokbot-voice"
KEYRING_USER = "xai"
_player_bin = None
_hotkeys = None


def config_dir():
    path = os.path.join(grok_store.xdg_config_home(), "grokbot-voice")
    return path


def saved_voice_path():
    return os.path.join(config_dir(), "voice.txt")


def tune_path():
    return os.path.join(config_dir(), "voice-settings.json")


def piper_dir():
    return os.path.join(config_dir(), "piper")


def chief_path():
    return os.path.join(config_dir(), "chief-of-staff.txt")


def log_path():
    cache = os.environ.get("XDG_CACHE_HOME", "").strip() or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(cache, "grokbot-voice", "log.txt")


def wav_path(name):
    cache = os.path.dirname(log_path())
    os.makedirs(cache, exist_ok=True)
    return os.path.join(cache, "grok_voice_%s.wav" % name)


def persistence_dir():
    return grok_store.linux_store(config_dir())


def key_help():
    return "Paste your xAI API key (from console.x.ai).\nIt's saved in your login keyring for this Linux account."


def load_key():
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
    except Exception:
        return ""


def save_key(key):
    import keyring
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key.strip())


def hide_console():
    return None


def apply_icon(root):
    try:
        import tkinter as tk
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        for path in (os.path.join(base, "icon.png"), os.path.join(base, "assets", "icon.png")):
            if os.path.isfile(path):
                image = tk.PhotoImage(file=path)
                root.iconphoto(True, image)
                root._icon_ref = image
                return
    except Exception:
        pass


def open_more_voices():
    import webbrowser
    webbrowser.open("https://huggingface.co/rhasspy/piper-voices")


def _espeak_bin():
    return shutil.which("espeak-ng") or shutil.which("espeak")


def voice_choices():
    choices = []
    if _espeak_bin():
        choices.append(("English (espeak-ng)", "espeak", "en"))
        choices.append(("English US (espeak-ng)", "espeak", "en-us"))
        choices.append(("English GB (espeak-ng)", "espeak", "en-gb"))
    else:
        choices.append(("English (espeak-ng)", "espeak", "en"))
    choices.extend(grok_store.piper_voice_choices(piper_dir()))
    return choices


def select_sapi(index):
    return None


def speak_sapi(text, speed, pitch, wait):
    return None


def pause_sapi():
    return False


def resume_sapi():
    return None


def sapi_is_paused():
    return False


def sapi_speaking():
    return False


def _is_tts_piper(path):
    try:
        result = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return False
    blob = ((result.stdout or "") + (result.stderr or "")).lower()
    return "output_file" in blob or "length_scale" in blob


def find_piper():
    env = os.environ.get("GROKBOT_PIPER", "").strip()
    local = os.path.join(piper_dir(), "piper")
    for path in (env, local):
        if path and os.path.isfile(path) and os.access(path, os.X_OK) and _is_tts_piper(path):
            return path
    found = shutil.which("piper")
    if found and _is_tts_piper(found):
        return found
    return None


def synthesize(kind, ref, text, speed, pitch, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if kind == "piper":
        binary = find_piper()
        if not binary:
            raise RuntimeError("Piper binary not found. Put it in %s" % piper_dir())
        ratio = pitch_ratio(pitch)
        length = ratio / max(0.3, float(speed))
        subprocess.run(
            [binary, "--model", ref, "--output_file", dest, "--length_scale", "%.4f" % length],
            input=text.encode("utf-8"),
            check=True,
        )
        scale_wav_rate(dest, ratio)
        return
    if kind == "espeak":
        binary = _espeak_bin()
        if not binary:
            raise RuntimeError("espeak-ng is not installed")
        wpm = max(80, min(450, int(round(175 * float(speed)))))
        espeak_pitch = max(0, min(99, int(round(50 + float(pitch) * 4))))
        subprocess.run(
            [binary, "-w", dest, "-s", str(wpm), "-p", str(espeak_pitch), "-v", str(ref)],
            input=text.encode("utf-8"),
            check=True,
        )
        return
    raise RuntimeError("Linux synthesizer got %s" % kind)


def _player_command(path):
    global _player_bin
    if _player_bin is None:
        for name in ("paplay", "pw-play", "aplay"):
            found = shutil.which(name)
            if found:
                _player_bin = found
                break
    if not _player_bin:
        return None
    return [_player_bin, path]


class LinuxAudio:
    """Play a WAV with paplay, pw-play, or aplay. Pause freezes that process."""

    def __init__(self):
        self.proc = None
        self.path = None
        self.sig_paused = False
        self._lock = threading.Lock()

    def stop(self):
        with self._lock:
            proc = self.proc
            self.proc = None
            self.sig_paused = False
        if proc is not None and proc.poll() is None:
            try:
                os.kill(proc.pid, signal.SIGCONT)
            except OSError:
                pass
            proc.kill()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass

    def arm(self, path):
        self.path = path

    def play(self, wait=False):
        path = self.path
        if not path:
            return
        self.stop()
        command = _player_command(path)
        if not command:
            raise RuntimeError("Install paplay (pulseaudio-utils) or pw-play (pipewire)")
        if wait:
            subprocess.run(command, check=False)
            return
        with self._lock:
            self.proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.sig_paused = False

    def pause(self):
        with self._lock:
            proc = self.proc
            if proc is None or proc.poll() is not None or self.sig_paused:
                return False
            os.kill(proc.pid, signal.SIGSTOP)
            self.sig_paused = True
            return True

    def resume(self):
        with self._lock:
            proc = self.proc
            if proc is not None and proc.poll() is None and self.sig_paused:
                os.kill(proc.pid, signal.SIGCONT)
                self.sig_paused = False
                return
            path = self.path
        if path:
            self.play(False)

    def is_active(self):
        with self._lock:
            proc = self.proc
        return proc is not None and proc.poll() is None


audio = LinuxAudio()


def stop_all_audio():
    audio.stop()


def read_chat():
    lines, names, _keys, _active = read_snapshot()
    return lines, names


def grok_window_titles():
    """Titles of Grok Bot windows. Empty when no title can be read."""
    titles = []
    commands = (
        ["xdotool", "search", "--class", "Grok Bot", "getwindowname"],
        ["xdotool", "search", "--classname", "grok-bot", "getwindowname"],
        ["wmctrl", "-l"],
    )
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0:
            continue
        for line in (result.stdout or "").splitlines():
            text = line.strip()
            if command[0] == "wmctrl":
                parts = text.split(None, 3)
                text = parts[-1].strip() if len(parts) >= 4 else ""
                if "grok" not in text.lower():
                    continue
            if not text or "grokbot voice" in text.lower():
                continue
            titles.append(text)
        if titles:
            return titles
    return []


def read_snapshot():
    """Lines, names, stable keys, and the active transcript path."""
    directory = persistence_dir()
    if not directory:
        return [], [], [], None
    try:
        titles = grok_window_titles()
    except Exception:
        titles = []
    return grok_store.reply_snapshot(directory, window_titles=titles)


def install_hotkeys(flags):
    """Global keys via pynput. Works on X11 (Mint Cinnamon's default) without root.

    Wayland does not deliver these events to ordinary apps, so the on-screen
    buttons are the fallback there. Failures are logged and the app still runs.
    """
    global _hotkeys
    try:
        from pynput.keyboard import GlobalHotKeys
    except Exception as exc:
        _log_hotkey(exc)
        return

    def toggle_pause():
        flags["pause"] = not flags["pause"]

    try:
        hotkeys = GlobalHotKeys({
            "<ctrl>+<alt>+s": lambda: flags.update(stop=True),
            "<ctrl>+<alt>+p": toggle_pause,
            "<ctrl>+<alt>+q": lambda: flags.update(quit=True),
        })
        hotkeys.daemon = True
        hotkeys.start()
        _hotkeys = hotkeys
    except Exception as exc:
        _log_hotkey(exc)


def _log_hotkey(exc):
    try:
        os.makedirs(os.path.dirname(log_path()), exist_ok=True)
        with open(log_path(), "a", encoding="utf-8") as handle:
            handle.write("hotkeys unavailable (%s). On Wayland, use the on-screen buttons.\n" % exc)
    except OSError:
        pass
