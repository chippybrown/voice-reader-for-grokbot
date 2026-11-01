# Grokbot Voice (automatic) for the Grok Bot desktop app on Windows.
# Shows a small always-on-top toolbar and speaks each new bot reply.
# Keyboard shortcuts still work from any window:
#   Ctrl+Alt+S = stop reading   Ctrl+Alt+P = pause/resume   Ctrl+Alt+Q = turn off
import os, time
import tkinter as tk
import keyboard
import comtypes.client
import uiautomation as auto

SPEED = 0          # -10 (slow) to 10 (fast), 0 is normal
SKIP_STARTS = ("Message", "You ", "Chip ", "Eldon ")  # not bot replies
SAVED = os.path.join(os.environ.get("APPDATA", "."), "Grok Reader voice.txt")
ASYNC, PURGE = 1, 2

voice = comtypes.client.CreateObject("SAPI.SpVoice")
voices = voice.GetVoices()
voice.Rate = SPEED

# ---- voice list: Windows voices + Piper natural voices ----
import glob, wave, threading, winsound
PIPER_DIR = os.path.join(os.environ.get("APPDATA", "."), "Grok Voice", "piper")
WAV = os.path.join(os.environ.get("TEMP", "."), "grok_voice_say.wav")
choices = []   # (label, kind, ref)
for i in range(voices.Count):
    label = voices.Item(i).GetDescription().replace("Microsoft ", "").split(" - ")[0]
    choices.append((label, "sapi", i))
piper_files = sorted(glob.glob(os.path.join(PIPER_DIR, "*.onnx")))
piper_keys = [os.path.basename(p).split("-")[1] for p in piper_files]
for f in piper_files:
    key = os.path.basename(f).split("-")[1]
    quality = os.path.basename(f)[:-5].split("-")[-1]
    nm = {"jenny_dioco": "Jenny", "ljspeech": "LJ Speech"}.get(key, key.replace("_", " ").title())
    if piper_keys.count(key) > 1 and quality != "medium":
        nm += " " + quality.title()
    choices.append((nm + " (natural)", "piper", f))

# ---- Grok voice: the chief of staff bot's own voice from the Grok Bot app ----
GV_DIR = os.path.join(os.environ.get("APPDATA", "."), "Grok Voice")
CHIEF_FILE = os.path.join(GV_DIR, "chief of staff.txt")   # bot whose voice reads everything
KEY_FILE = os.path.join(GV_DIR, "xai key.bin")             # xAI API key, encrypted for this Windows user
def chief_name():
    try:
        return open(CHIEF_FILE).read().strip() or "Moya"
    except Exception:
        return "Moya"
def chief_voice(name):
    """Read the bot's saved voice (e.g. carina) from the Grok Bot app's local data."""
    import re as _re
    d = os.path.join(os.environ.get("APPDATA", "."), "Grok Bot", "sand-client-persistence")
    pat = _re.compile(r'\{"id":"[0-9a-f-]{36}","name":"%s"' % _re.escape(name))
    vpat = _re.compile(r'"voiceId":"([a-z]+)","voiceSpeed":([\d.]+)')
    for f in glob.glob(os.path.join(d, "*.blob")):
        try:
            t = open("\\\\?\\" + os.path.abspath(f), encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for m in pat.finditer(t):
            v = vpat.search(t, m.end(), m.end() + 8000)
            if v:
                return v.group(1), float(v.group(2))
    return ("carina", 1.0) if name == "Moya" else (None, 1.0)

import ctypes as _ct
from ctypes import wintypes as _wt
class _BLOB(_ct.Structure):
    _fields_ = [("cbData", _wt.DWORD), ("pbData", _ct.POINTER(_ct.c_char))]
def _dpapi(data, protect):
    src = _BLOB(len(data), _ct.cast(_ct.create_string_buffer(data, len(data)), _ct.POINTER(_ct.c_char)))
    out = _BLOB()
    fn = _ct.windll.crypt32.CryptProtectData if protect else _ct.windll.crypt32.CryptUnprotectData
    if not fn(_ct.byref(src), None, None, None, None, 0, _ct.byref(out)):
        raise OSError("Windows could not protect the key")
    res = _ct.string_at(out.pbData, out.cbData)
    _ct.windll.kernel32.LocalFree(out.pbData)
    return res
def load_key():
    try:
        return _dpapi(open(KEY_FILE, "rb").read(), False).decode()
    except Exception:
        return ""
def save_key(k):
    os.makedirs(GV_DIR, exist_ok=True)
    open(KEY_FILE, "wb").write(_dpapi(k.strip().encode(), True))

_chief = chief_name()
_cv, _cspeed = chief_voice(_chief)
if _cv:
    choices.insert(0, ("%s's voice (Grok)" % _chief, "grok", _cv))

def grok_audio(text, voice_id, speed):
    """Ask xAI's speech service for 24 kHz 16-bit PCM in the given voice."""
    import urllib.request
    body = json.dumps({"text": text, "voice_id": voice_id, "language": "auto",
                       "speed": max(0.7, min(1.5, speed)),
                       "output_format": {"codec": "pcm", "sample_rate": 24000}}).encode()
    req = urllib.request.Request("https://api.x.ai/v1/tts", data=body, method="POST", headers={
        "Authorization": "Bearer " + load_key(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

piper_cache = {}
speak_state = {"kind": "sapi", "ref": 0, "token": 0, "busy_until": 0.0, "making": False}

import json
from xml.sax.saxutils import escape
TUNE_FILE = os.path.join(os.environ.get("APPDATA", "."), "Grok Voice", "voice settings.json")
try:
    tune_all = json.load(open(TUNE_FILE))
except Exception:
    tune_all = {}
def tune():   # current voice's {"speed": 0.5..2.0, "pitch": -10..10}
    t = tune_all.setdefault(speak_state.get("label", ""), {})
    t.setdefault("speed", 1.0); t.setdefault("pitch", 0)
    return t
def save_tune():
    os.makedirs(os.path.dirname(TUNE_FILE), exist_ok=True)
    json.dump(tune_all, open(TUNE_FILE, "w"), indent=1)

def use_choice(i):
    label, kind, ref = choices[i]
    speak_state["kind"], speak_state["ref"], speak_state["label"] = kind, ref, label
    if kind == "sapi":
        voice.Voice = voices.Item(ref)

saved_label = ""
try:
    saved_label = open(SAVED).read().strip()
except Exception:
    pass
saved = next((i for i, ch in enumerate(choices) if ch[0] == saved_label), 0)
use_choice(saved)

def stop_all():
    speak_state["token"] += 1
    speak_state["busy_until"] = 0.0
    speak_state["held"] = False
    if speak_state.pop("sapi_paused", False):
        voice.Resume()
    voice.Speak("", ASYNC | PURGE)
    winsound.PlaySound(None, 0)

def piper_job(text, token, wait):
    try:
        ref = speak_state["ref"]
        if speak_state["kind"] == "grok":
            try:
                if not load_key():
                    raise RuntimeError("no xAI key set")
                pcm = grok_audio(text, ref, tune()["speed"])
                if token != speak_state["token"]:
                    return
                params = wave._wave_params(1, 2, 24000, len(pcm) // 2, "NONE", "not compressed")
                with wave.open(WAV, "wb") as w:
                    w.setparams(params); w.writeframes(pcm)
                secs = len(pcm) / 48000.0
                speak_state["audio"] = (params, pcm)
                speak_state["offset"] = 0.0
                if speak_state.get("paused"):
                    return
                speak_state["play_start"] = time.time()
                speak_state["busy_until"] = time.time() + secs
                winsound.PlaySound(WAV, winsound.SND_FILENAME | (0 if wait else winsound.SND_ASYNC))
                return
            except Exception as e:
                log("Grok voice problem, using a local voice: %r" % (e,))
                ref = next((c[2] for c in choices if c[1] == "piper" and c[0].startswith("Jenny")),
                           next((c[2] for c in choices if c[1] == "piper"), None))
                if ref is None:
                    return
        if ref not in piper_cache:
            from piper import PiperVoice
            piper_cache[ref] = PiperVoice.load(ref)
        from piper import SynthesisConfig
        t = tune()
        shift = 2 ** ((t["pitch"] * 0.6) / 12.0)          # pitch shift by playing faster/slower
        cfg = SynthesisConfig(length_scale=shift / max(0.3, t["speed"]))
        with wave.open(WAV, "wb") as w:
            piper_cache[ref].synthesize_wav(text, w, syn_config=cfg)
        with wave.open(WAV, "rb") as w:
            params, frames = w.getparams(), w.readframes(w.getnframes())
        rate = int(params.framerate * shift)
        with wave.open(WAV, "wb") as w:
            w.setparams(params._replace(framerate=rate))
            w.writeframes(frames)
        secs = params.nframes / float(rate)
        if token != speak_state["token"]:
            return
        speak_state["audio"] = (params._replace(framerate=rate), frames)
        speak_state["offset"] = 0.0
        if speak_state.get("paused"):
            return   # paused while the audio was being made: wait for Resume
        speak_state["play_start"] = time.time()
        speak_state["busy_until"] = time.time() + secs
        winsound.PlaySound(WAV, winsound.SND_FILENAME | (0 if wait else winsound.SND_ASYNC))
    except Exception as e:
        print("Piper problem:", e)
        log("Piper problem: %r" % (e,))
    finally:
        if token == speak_state["token"]:
            speak_state["making"] = False

LOG = os.path.join(os.environ.get("TEMP", "."), "grokbot_voice_log.txt")
def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass

def say(text, wait=False):
    if text:
        log("speak [%s] %s" % (speak_state.get("label", "?"), text[:60].replace("\n", " ")))
    stop_all()
    if not text:
        return
    speak_state["paused"] = False   # Back/Next/new reply while paused: play it and leave pause
    flags["pause"] = False
    if speak_state["kind"] == "sapi":
        t = tune()
        voice.Rate = max(-10, min(10, round((t["speed"] - 1.0) * 10)))
        xml = '<pitch absmiddle="%d">%s</pitch>' % (t["pitch"], escape(text))
        voice.Speak(xml, (0 if wait else ASYNC | PURGE) | 8)
        return
    speak_state["making"] = True
    tok = speak_state["token"]
    if wait:
        piper_job(text, tok, True)
    else:
        threading.Thread(target=piper_job, args=(text, tok, False), daemon=True).start()

WAV2 = os.path.join(os.environ.get("TEMP", "."), "grok_voice_resume.wav")
def pause_audio():
    """Pause mid-reply and remember the spot."""
    speak_state["paused"] = True
    if speak_state["kind"] == "sapi":
        if voice.Status.RunningState == 2:
            voice.Pause()
            speak_state["sapi_paused"] = True
        return
    if time.time() < speak_state["busy_until"] and speak_state.get("audio"):
        speak_state["offset"] += time.time() - speak_state.get("play_start", time.time())
        speak_state["busy_until"] = 0.0
        winsound.PlaySound(None, 0)
        speak_state["held"] = True
    elif speak_state["making"]:
        speak_state["held"] = True   # audio still being made; it will wait

def resume_audio():
    """Carry on from the remembered spot."""
    speak_state["paused"] = False
    if speak_state["kind"] == "sapi":
        if speak_state.pop("sapi_paused", False):
            voice.Resume()
        return
    if not speak_state.pop("held", False):
        return
    if speak_state["making"]:
        return   # job will play it when done
    params, frames = speak_state["audio"]
    width = params.sampwidth * params.nchannels
    start = int(speak_state["offset"] * params.framerate) * width
    rest = frames[start:]
    if not rest:
        return
    with wave.open(WAV2, "wb") as w:
        w.setparams(params)
        w.writeframes(rest)
    secs = len(rest) / float(width * params.framerate)
    speak_state["play_start"] = time.time()
    speak_state["busy_until"] = time.time() + secs
    winsound.PlaySound(WAV2, winsound.SND_FILENAME | winsound.SND_ASYNC)

def is_speaking():
    if speak_state.get("held") or speak_state.get("sapi_paused"):
        return True   # paused mid-reply still counts as this reply
    if speak_state["kind"] == "sapi":
        return voice.Status.RunningState == 2
    return speak_state["making"] or time.time() < speak_state["busy_until"]

flags = {"stop": False, "back": False, "skip": False, "pause": False, "quit": False, "play": False}
keyboard.add_hotkey("ctrl+alt+s", lambda: flags.update(stop=True))
keyboard.add_hotkey("ctrl+alt+p", lambda: flags.update(pause=not flags["pause"]))
keyboard.add_hotkey("ctrl+alt+q", lambda: flags.update(quit=True))

def bot_replies():
    win = auto.WindowControl(searchDepth=1, Name="Grok Bot")
    if not win.Exists(0, 0):
        return []
    found, inside = [], False
    for ctrl, depth in auto.WalkControl(win, maxDepth=60):
        if ctrl.ControlTypeName != "GroupControl":
            continue
        name = (ctrl.Name or "").strip()
        if name == "Conversation transcript":
            inside = True
            continue
        if name in ("Conversation details", "Computer preview"):
            inside = False
        if inside and " " in name and len(name) > 15 and not name.startswith(SKIP_STARTS):
            if not announce(name).strip():
                continue   # just a timestamp like "Cameron 6:50:11 AM", nothing to read
            found.append(name)
    return found

# Bot names, longest first, so "Vision Design 3.0" wins over "Vision".
BOT_NAMES = sorted(["Moya", "Research Bot", "Grass Hopper", "Time Card", "Design Bot", "Finance Bot",
    "Radar", "Stock Bot", "My Life Bot", "Piper", "Jenny's Bot", "Money Bot", "Remote Access Bot",
    "Cameron", "Vision Design 3.0", "E Watcher", "HA Fixer", "Vision", "Gideon", "Grok Bot",
    "Estimating Bot", "Doc Bot", "Vision Bot", "Appian Bot Vision"], key=len, reverse=True)
import re
TIME_RE = re.compile(r"\b(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*,?\s+)?(?:\w{3,9}\s+\d{1,2},?\s+)?\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\b")
def announce(reply):
    """'Cameron 6:50 AM Hello there' -> 'Hello there' (no bot name, no time)"""
    text = next((reply[len(n) + 1:] for n in BOT_NAMES if reply.startswith(n + " ")), None)
    if text is None:
        text = reply.partition(" ")[2]
    text = text.strip()
    m = TIME_RE.match(text)            # time at the start
    if m:
        text = text[m.end():].strip()
    m = re.search(TIME_RE.pattern + r"\s*$", text)   # time at the end
    if m:
        text = text[:m.start()].strip()
    return text

# ---------- toolbar (rounded, dark, draggable) ----------
import ctypes
try:  # hide the black console window if one opened
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)
except Exception:
    pass

BG, PANEL, FG, DIM, ACCENT, RED, KEY = "#1f2430", "#2a3040", "#e8ecf4", "#8a93a6", "#4cc38a", "#ff6b6b", "#ff00fe"
W, H = 300, 74
root = tk.Tk()
root.title("Grokbot Voice")
try:
    import sys as _sys
    root.iconbitmap(os.path.join(getattr(_sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "grokbot_voice.ico"))
except Exception:
    pass
root.overrideredirect(True)
root.attributes("-topmost", True)
root.attributes("-transparentcolor", KEY)
root.configure(bg=KEY)
sw = root.winfo_screenwidth()
sh = root.winfo_screenheight()
root.geometry(f"{W}x{H}+{int(sw - W - sw * 0.10)}+{int(sh - H - sh * 0.05)}")

c = tk.Canvas(root, width=W, height=H, bg=KEY, highlightthickness=0)
c.pack()
def rounded(x1, y1, x2, y2, r, **kw):
    pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2, x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
    return c.create_polygon(pts, smooth=True, **kw)
rounded(1, 1, W-1, H-1, 22, fill=BG, outline="#3a4256")

# title + status
c.create_text(16, 16, text="🔊  Grokbot Voice", anchor="w", fill=FG, font=("Segoe UI Semibold", 10))
dot = c.create_oval(138, 11, 148, 21, fill=ACCENT, outline="")
stxt = c.create_text(152, 16, text="Watching", anchor="w", fill=DIM, font=("Segoe UI", 9))
status = tk.StringVar(value="Watching")
LABELS = {"Stopped": "Not monitoring", "Paused": "Reading paused"}
btn = {}   # name -> (circle, glyph)
def base_fill(name):
    v = status.get()
    if name == "stop" and v == "Stopped":
        return RED
    if name == "pause" and v == "Paused":
        return "#f5b942"
    return PANEL
def show_status(*_):
    v = status.get()
    c.itemconfig(stxt, text=LABELS.get(v, v))
    c.itemconfig(dot, fill={"Watching": ACCENT, "Reading": "#5aa9ff", "Paused": "#f5b942", "Stopped": RED}.get(v, DIM))
    for name, (b, t) in btn.items():
        c.itemconfig(b, fill=base_fill(name))
    if "pause" in btn:
        c.itemconfig(btn["pause"][1], fill="#1f2430" if v == "Paused" else FG)
    if "play" in btn:   # green only while monitoring
        c.itemconfig(btn["play"][1], fill=ACCENT if v in ("Watching", "Reading") else DIM)
status.trace_add("write", show_status)

# drag anywhere on the background
drag = {}
def press(e): drag.update(x=e.x, y=e.y)
def move(e): root.geometry(f"+{root.winfo_x() + e.x - drag['x']}+{root.winfo_y() + e.y - drag['y']}")
c.bind("<Button-1>", press); c.bind("<B1-Motion>", move)

# round icon buttons
def icon_button(x, glyph, tip, action, color=FG, y=50, r=15, size=12, name=None):
    b = c.create_oval(x-r, y-r, x+r, y+r, fill=PANEL, outline="")
    t = c.create_text(x, y, text=glyph, fill=color, font=("Segoe UI Symbol", size))
    if name:
        btn[name] = (b, t)
    for item in (b, t):
        c.tag_bind(item, "<Enter>", lambda e: (c.itemconfig(b, fill="#3a4256"), c.itemconfig(stxt, text=tip)))
        c.tag_bind(item, "<Leave>", lambda e: show_status())
        c.tag_bind(item, "<Button-1>", lambda e: action())
icon_button(70,  "\u23EE", "Back", lambda: flags.update(back=True))
icon_button(110, "\u25A0", "Stop", lambda: flags.update(stop=True), name="stop")
icon_button(150, "\u275A\u275A", "Pause", lambda: flags.update(pause=True), name="pause")
icon_button(190, "\u25B6", "Play / Resume", lambda: flags.update(pause=False, play=True), ACCENT, name="play")
show_status()
icon_button(230, "\u23ED", "Next", lambda: flags.update(skip=True))
icon_button(W-50, "\u2699", "Settings", lambda: open_tuner(), y=17, r=11, size=10)
icon_button(W-22, "\u23FB", "Turn off", lambda: flags.update(quit=True), RED, y=17, r=11, size=10)

tuner = {"win": None}
def open_tuner():
    if tuner["win"] is not None:
        tuner["win"].destroy(); tuner["win"] = None
        return
    t = tune()
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg=BG, highlightthickness=1, highlightbackground="#3a4256")
    tk.Label(win, text="\u2699  Settings", bg=BG, fg=FG, font=("Segoe UI Semibold", 9)).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 2))
    tk.Label(win, text="Voice", bg=BG, fg=DIM, font=("Segoe UI", 9), width=6, anchor="w").grid(row=4, column=0, padx=(10, 0), pady=(4, 2))
    vb = tk.Button(win, text="\U0001F3A4 " + speak_state["label"] + "  \u25BE", bg=PANEL, fg=FG, activebackground="#3a4256", activeforeground=FG,
                   relief="flat", bd=0, padx=10, pady=3, font=("Segoe UI", 9), anchor="w", width=28)
    vb.configure(command=lambda: menu.tk_popup(vb.winfo_rootx(), vb.winfo_rooty() + vb.winfo_height()))
    vb.grid(row=4, column=1, padx=(0, 10), pady=(4, 2), sticky="w")
    def slider(row, label, lo, hi, res, val, key):
        tk.Label(win, text=label, bg=BG, fg=DIM, font=("Segoe UI", 9), width=6, anchor="w").grid(row=row, column=0, padx=(10, 0))
        sc = tk.Scale(win, from_=lo, to=hi, resolution=res, orient="horizontal", length=200,
                      bg=BG, fg=FG, troughcolor=PANEL, highlightthickness=0, bd=0,
                      activebackground=ACCENT, sliderrelief="flat", font=("Segoe UI", 8))
        sc.set(val)
        sc.grid(row=row, column=1, padx=(0, 10))
        def changed(v): tune()[key] = float(v) if key == "speed" else int(float(v)); save_tune()
        sc.configure(command=changed)
    slider(1, "Speed", 0.5, 2.0, 0.1, t["speed"], "speed")
    slider(2, "Pitch", -10, 10, 1, t["pitch"], "pitch")
    bar2 = tk.Frame(win, bg=BG); bar2.grid(row=5, column=0, columnspan=2, pady=(6, 8))
    def reset():
        tune_all[speak_state["label"]] = {"speed": 1.0, "pitch": 0}; save_tune(); win.destroy(); tuner["win"] = None; open_tuner()
    for txt, cmd in (("\u25B6 Test", lambda: say("This is how I sound now.")), ("Reset", reset), ("Done", lambda: (win.destroy(), tuner.update(win=None)))):
        tk.Button(bar2, text=txt, command=cmd, bg=PANEL, fg=FG, activebackground="#3a4256", activeforeground=FG,
                  relief="flat", bd=0, padx=10, pady=3, font=("Segoe UI", 9)).pack(side="left", padx=4)
    win.update_idletasks()
    win.geometry(f"+{root.winfo_x() + W - win.winfo_width()}+{root.winfo_y() - win.winfo_height() - 8}")
    tuner["win"] = win

# voice switcher (click to cycle voices)
short = [ch[0] for ch in choices]
def set_voice(i):
    use_choice(i)
    open(SAVED, "w").write(short[i])
    if tuner["win"] is not None:   # refresh the settings panel for the new voice
        tuner["win"].destroy(); tuner["win"] = None
        open_tuner()
menu = tk.Menu(root, tearoff=0, bg=PANEL, fg=FG, activebackground="#3a4256", activeforeground=FG, font=("Segoe UI", 9))
for i, n in enumerate(short):
    menu.add_command(label=n, command=lambda i=i: set_voice(i))
menu.add_separator()
menu.add_command(label="\u2795  Get More Voices...", command=lambda: os.startfile("ms-settings:speech"))
def key_dialog():
    win = tk.Toplevel(root); win.title("xAI API key"); win.configure(bg=PANEL); win.attributes("-topmost", True)
    tk.Label(win, text="Paste your xAI API key (from console.x.ai).\nIt's saved encrypted for your Windows account only.",
             bg=PANEL, fg=FG, font=("Segoe UI", 9), justify="left").pack(padx=12, pady=(10, 6), anchor="w")
    e = tk.Entry(win, show="\u2022", width=44, bg="#11151c", fg=FG, insertbackground=FG, relief="flat")
    e.pack(padx=12, pady=4); e.focus_set()
    def ok():
        k = e.get().strip()
        if k:
            save_key(k)
            gi = next((i for i, ch in enumerate(choices) if ch[1] == "grok"), None)
            if gi is not None:
                set_voice(gi)
        win.destroy()
    tk.Button(win, text="Save", command=ok, bg=ACCENT, fg="white", relief="flat", padx=14).pack(pady=(6, 10))
    win.bind("<Return>", lambda ev: ok())
menu.add_command(label="\U0001F511  Set xAI API key...", command=key_dialog)

# ---------- watcher loop ----------
_first = bot_replies()
state = {"seen": set(_first), "history": list(_first), "pos": None, "queue": [], "paused": False, "stopped": False, "next": 0}

def tick():
    if flags["quit"]:
        say("")
        root.destroy()
        return
    if flags["stop"]:            # Stop: end this reply and stop watching until Play
        flags["stop"] = False
        state["queue"].clear()
        state["stopped"] = True
        flags["pause"] = False
        state["paused"] = False
        say("")
    if flags["play"]:
        flags["play"] = False
        if state["stopped"]:     # back to watching; anything that came in while stopped is skipped
            state["stopped"] = False
            state["seen"].update(bot_replies())
            state["prev_cur"] = list(bot_replies())
    if flags["back"]:
        flags["back"] = False
        h = state["history"]
        if h:
            state["pos"] = len(h) - 1 if state["pos"] is None else max(0, state["pos"] - 1)
            state["queue"].clear()
            say(announce(h[state["pos"]]))
    if flags["skip"]:   # Next
        flags["skip"] = False
        h = state["history"]
        if state["pos"] is not None and state["pos"] < len(h) - 1:
            state["pos"] += 1          # step forward through history
            state["queue"].clear()
            say(announce(h[state["pos"]]))
        else:
            # stop the current reply now and go back to watching for a new one
            state["queue"].clear()
            state["pos"] = None
            say("")
    if flags["pause"] != state["paused"]:
        state["paused"] = flags["pause"]
        if state["paused"]:
            pause_audio()       # silent; remembers the spot in this reply
        else:
            resume_audio()      # carry on from that spot, then keep watching
            state["seen"].update(bot_replies())   # skip what came in while paused
    if not state["paused"] and not state["stopped"] and time.time() >= state["next"]:
        state["next"] = time.time() + 1
        try:
            cur = bot_replies()
            seen = state["seen"]
            known = [i for i, r in enumerate(cur) if r in seen]
            prev = state.get("prev_cur", [])
            if cur:
                state["prev_cur"] = list(cur)   # keep the last real view while a chat loads
            def who(r):
                return next((n for n in BOT_NAMES if r.startswith(n + " ")), r.partition(" ")[0])
            switched = bool(cur) and (
                (prev and not set(prev) & set(cur))                 # nothing in common with the last chat
                or (prev and who(prev[-1]) != who(cur[-1]))         # a different bot is on screen
                or (not known and (prev or len(cur) > 1)))
            if switched:
                # new bot or chat: cut off the old read now, start at the bottom, all above counts as read
                seen.update(cur)
                state["history"] = list(cur)
                state["queue"].clear()
                # read only the bottom reply of the new chat; Back steps up from there
                state["pos"] = len(cur) - 1
                say(announce(cur[-1]))
            else:
                last_known = known[-1] if known else -1
                for i, reply in enumerate(cur):
                    if reply in seen:
                        continue
                    seen.add(reply)
                    if i < last_known:
                        continue   # older message (scrolled into view), not new
                    state["history"].append(reply)
                    state["pos"] = None
                    state["queue"].append(reply)
        except Exception:
            pass
    speaking = is_speaking()
    if state["queue"] and not speaking and not state["paused"] and not state["stopped"]:
        say(announce(state["queue"].pop(0)))
        speaking = True
    if state["stopped"] and not speaking:
        new = "Stopped"
    elif state["paused"]:
        new = "Paused"
    else:
        new = "Reading" if speaking else "Watching"
    if status.get() != new:
        status.set(new)
    root.after(200, tick)

root.after(200, tick)
root.mainloop()
