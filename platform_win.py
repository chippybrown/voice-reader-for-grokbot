# Windows pieces: SAPI, UI Automation, DPAPI, winsound, and the keyboard library.
import os
import sys
import time
import wave

import grok_store
from audio_util import pitch_ratio, scale_wav_rate

ASYNC, PURGE = 1, 2


def _appdata():
    return os.environ.get("APPDATA", ".")


def config_dir():
    path = os.path.join(_appdata(), "Grok Voice")
    return path


def saved_voice_path():
    return os.path.join(_appdata(), "Grok Reader voice.txt")


def tune_path():
    return os.path.join(config_dir(), "voice settings.json")


def piper_dir():
    return os.path.join(config_dir(), "piper")


def chief_path():
    return os.path.join(config_dir(), "chief of staff.txt")


def log_path():
    return os.path.join(os.environ.get("TEMP", "."), "grokbot_voice_log.txt")


def wav_path(name):
    return os.path.join(os.environ.get("TEMP", "."), "grok_voice_%s.wav" % name)


def persistence_dir():
    return os.path.join(_appdata(), "Grok Bot", grok_store.PERSISTENCE_NAME)


def key_help():
    return "Paste your xAI API key (from console.x.ai).\nIt's saved encrypted for your Windows account only."


def load_key():
    try:
        return _dpapi(open(os.path.join(config_dir(), "xai key.bin"), "rb").read(), False).decode()
    except Exception:
        return ""


def save_key(key):
    os.makedirs(config_dir(), exist_ok=True)
    path = os.path.join(config_dir(), "xai key.bin")
    open(path, "wb").write(_dpapi(key.strip().encode(), True))


def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    src = Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("Windows could not protect the key")
    result = ctypes.string_at(out.pbData, out.cbData)
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return result


def hide_console():
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def apply_icon(root):
    try:
        root.iconbitmap(os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "grokbot_voice.ico"))
    except Exception:
        pass


def open_more_voices():
    os.startfile("ms-settings:speech")


_sapi = None
_sapi_voices = None
_sapi_paused = False


def _voice():
    global _sapi, _sapi_voices
    if _sapi is None:
        import comtypes.client
        _sapi = comtypes.client.CreateObject("SAPI.SpVoice")
        _sapi_voices = _sapi.GetVoices()
        _sapi.Rate = 0
    return _sapi


def voice_choices():
    choices = []
    voice = _voice()
    voices = _sapi_voices
    for index in range(voices.Count):
        label = voices.Item(index).GetDescription().replace("Microsoft ", "").split(" - ")[0]
        choices.append((label, "sapi", index))
    choices.extend(grok_store.piper_voice_choices(piper_dir()))
    return choices


def select_sapi(index):
    voice = _voice()
    voice.Voice = _sapi_voices.Item(index)


def speak_sapi(text, speed, pitch, wait):
    from xml.sax.saxutils import escape
    voice = _voice()
    voice.Rate = max(-10, min(10, round((speed - 1.0) * 10)))
    xml = '<pitch absmiddle="%d">%s</pitch>' % (pitch, escape(text))
    voice.Speak(xml, (0 if wait else ASYNC | PURGE) | 8)


def pause_sapi():
    global _sapi_paused
    voice = _voice()
    if voice.Status.RunningState == 2:
        voice.Pause()
        _sapi_paused = True
        return True
    return False


def resume_sapi():
    global _sapi_paused
    if _sapi_paused:
        _sapi_paused = False
        _voice().Resume()


def sapi_is_paused():
    return _sapi_paused


def sapi_speaking():
    return _voice().Status.RunningState == 2


def stop_all_audio():
    global _sapi_paused
    if _sapi_paused:
        _sapi_paused = False
        try:
            _voice().Resume()
        except Exception:
            pass
    try:
        _voice().Speak("", ASYNC | PURGE)
    except Exception:
        pass
    audio.stop()


class WinAudio:
    """winsound cannot pause a file, so pause remembers the sample and resume plays the rest."""

    def __init__(self):
        self.params = None
        self.frames = None
        self.offset = 0.0
        self.play_start = 0.0
        self.busy_until = 0.0
        self.paused = False
        self.path = wav_path("say")
        self.tail = wav_path("resume")

    def stop(self):
        import winsound
        self.busy_until = 0.0
        self.paused = False
        self.frames = None
        winsound.PlaySound(None, 0)

    def arm(self, path):
        with wave.open(path, "rb") as handle:
            self.params = handle.getparams()
            self.frames = handle.readframes(handle.getnframes())
        self.offset = 0.0
        self.path = path
        self.paused = False

    def play(self, wait=False):
        import winsound
        if not self.params:
            return
        seconds = self.params.nframes / float(self.params.framerate or 1)
        self.play_start = time.time()
        self.busy_until = time.time() + seconds
        flags = winsound.SND_FILENAME | (0 if wait else winsound.SND_ASYNC)
        winsound.PlaySound(self.path, flags)

    def pause(self):
        import winsound
        if time.time() < self.busy_until and self.frames:
            self.offset += time.time() - self.play_start
            self.busy_until = 0.0
            winsound.PlaySound(None, 0)
            self.paused = True
            return True
        return False

    def resume(self):
        import winsound
        if not self.frames or not self.params:
            return
        self.paused = False
        width = self.params.sampwidth * self.params.nchannels
        start = int(self.offset * self.params.framerate) * width
        rest = self.frames[start:]
        if not rest:
            return
        with wave.open(self.tail, "wb") as handle:
            handle.setparams(self.params)
            handle.writeframes(rest)
        seconds = len(rest) / float(width * self.params.framerate)
        self.play_start = time.time()
        self.busy_until = time.time() + seconds
        winsound.PlaySound(self.tail, winsound.SND_FILENAME | winsound.SND_ASYNC)

    def is_active(self):
        return self.paused or time.time() < self.busy_until


audio = WinAudio()

_piper_cache = {}


def synthesize(kind, ref, text, speed, pitch, dest):
    if kind != "piper":
        raise RuntimeError("Windows synthesizer got %s" % kind)
    if ref not in _piper_cache:
        from piper import PiperVoice
        _piper_cache[ref] = PiperVoice.load(ref)
    from piper import SynthesisConfig
    ratio = pitch_ratio(pitch)
    config = SynthesisConfig(length_scale=ratio / max(0.3, speed))
    with wave.open(dest, "wb") as handle:
        _piper_cache[ref].synthesize_wav(text, handle, syn_config=config)
    scale_wav_rate(dest, ratio)


def read_chat():
    """Replies visible in the Grok Bot window.

    Windows does not parse the saved transcript, so it never sees the
    toAgent field. Outbound notes to other agents are a file-format
    distinction. The on-screen reader skips user bubbles and any control
    whose name carries an agent-outbound id.
    """
    import uiautomation as auto
    win = auto.WindowControl(searchDepth=1, Name="Grok Bot")
    if not win.Exists(0, 0):
        return [], []
    found, inside = [], False
    skip = ("Message", "You ", "Chip ", "Eldon ")
    for ctrl, depth in auto.WalkControl(win, maxDepth=60):
        if ctrl.ControlTypeName != "GroupControl":
            continue
        name = (ctrl.Name or "").strip()
        if name == "Conversation transcript":
            inside = True
            continue
        if name in ("Conversation details", "Computer preview"):
            inside = False
        if "agent-outbound" in name or "toAgent" in name:
            continue
        if inside and " " in name and len(name) > 15 and not name.startswith(skip):
            found.append(name)
    return found, []


def grok_window_titles():
    """The Grok Bot window title, when UI Automation can see it."""
    try:
        import uiautomation as auto
        win = auto.WindowControl(searchDepth=1, Name="Grok Bot")
        if win.Exists(0, 0):
            title = (win.Name or "").strip()
            if title:
                return [title]
    except Exception:
        pass
    return []


def read_snapshot():
    """The open chat from saved files, with the window title as a hint.

    The on-screen walk is only used when Grok Bot has not saved a store yet.
    """
    directory = persistence_dir()
    if directory and os.path.isdir(directory):
        try:
            titles = grok_window_titles()
        except Exception:
            titles = []
        return grok_store.reply_snapshot(directory, window_titles=titles)
    lines, names = read_chat()
    return lines, names, [[line] for line in lines], None


def install_hotkeys(flags):
    import keyboard
    keyboard.add_hotkey("ctrl+alt+s", lambda: flags.update(stop=True))
    keyboard.add_hotkey("ctrl+alt+p", lambda: flags.update(pause=not flags["pause"]))
    keyboard.add_hotkey("ctrl+alt+q", lambda: flags.update(quit=True))

