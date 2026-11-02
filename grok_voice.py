# Grokbot Voice for the Grok Bot desktop app.
# A small always-on-top toolbar speaks each new bot reply.
# Windows reads the Grok Bot window. Linux reads the app's saved chat files.
# Keyboard shortcuts still work from any window on Windows, and on Linux Mint's
# usual X11 session:
#   Ctrl+Alt+S = stop reading   Ctrl+Alt+P = pause/resume   Ctrl+Alt+Q = turn off
import json
import os
import sys
import threading
import time
import tkinter as tk
import urllib.request

if sys.platform == "win32":
    import platform_win as platform
else:
    import platform_linux as platform

import bot_prefs
import grok_store
import piper_setup
import single_instance
import updates
import window_layout
from audio_util import write_pcm_wav
from version import APP_TITLE, VERSION

# Claim the single-instance lock before hotkeys, settings, or the window.
# A second start exits here, so it never speaks. The first window is raised.
_window = {}

def _another_launch():
    window = _window.get("root")
    if window is None:
        return
    def raise_window():
        try:
            window.lift()
            window.attributes("-topmost", True)
        except Exception:
            pass
    try:
        window.after(0, raise_window)
    except Exception:
        pass

_instance = single_instance.InstanceLock(platform.config_dir())
if os.environ.get("GROKBOT_VOICE_SELFTEST") != "1" and not _instance.claim(_another_launch):
    sys.exit(0)

SAVED = platform.saved_voice_path()
TUNE_FILE = platform.tune_path()
WAV = platform.wav_path("say")

choices = platform.voice_choices()   # (label, kind, ref)

def chief_name():
    try:
        return open(platform.chief_path(), encoding="utf-8").read().strip() or "Moya"
    except Exception:
        return "Moya"

_chief = chief_name()
_cv, _cspeed = grok_store.chief_voice(platform.persistence_dir(), _chief)
if _cv:
    choices.insert(0, ("%s's voice (Grok)" % _chief, "grok", _cv))
if not choices:
    choices.append(("English (espeak-ng)", "espeak", "en"))

def grok_audio(text, voice_id, speed):
    """Ask xAI's speech service for 24 kHz 16-bit PCM in the given voice."""
    body = json.dumps({"text": text, "voice_id": voice_id, "language": "auto",
                       "speed": max(0.7, min(1.5, speed)),
                       "output_format": {"codec": "pcm", "sample_rate": 24000}}).encode()
    req = urllib.request.Request("https://api.x.ai/v1/tts", data=body, method="POST", headers={
        "Authorization": "Bearer " + platform.load_key(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()

speak_state = {"kind": "sapi", "ref": 0, "token": 0, "busy_until": 0.0, "making": False}

try:
    tune_all = json.load(open(TUNE_FILE, encoding="utf-8"))
except Exception:
    tune_all = {}

def voice_tune(label):
    """Speed and pitch saved for one voice label."""
    saved = tune_all.setdefault(label or "", {})
    saved.setdefault("speed", 1.0)
    saved.setdefault("pitch", 0)
    return saved

def tune():   # voice in use, or this bot's own speed and pitch when set
    base = voice_tune(speak_state.get("label", ""))
    if "bot_speed" not in speak_state and "bot_pitch" not in speak_state:
        return base
    return {
        "speed": speak_state.get("bot_speed", base["speed"]),
        "pitch": speak_state.get("bot_pitch", base["pitch"]),
    }

def save_tune():
    os.makedirs(os.path.dirname(TUNE_FILE), exist_ok=True)
    json.dump(tune_all, open(TUNE_FILE, "w", encoding="utf-8"), indent=1)

def use_choice(i):
    label, kind, ref = choices[i]
    speak_state["kind"], speak_state["ref"], speak_state["label"] = kind, ref, label
    if kind == "sapi":
        platform.select_sapi(ref)

saved_label = ""
try:
    saved_label = open(SAVED, encoding="utf-8").read().strip()
except Exception:
    pass
saved = piper_setup.preferred_index([ch[0] for ch in choices], saved_label)
use_choice(saved)

BOT_FILE = os.path.join(platform.config_dir(), "bot settings.json")

def load_bot_prefs():
    try:
        return bot_prefs.normalize(json.load(open(BOT_FILE, encoding="utf-8")))
    except Exception:
        return bot_prefs.fresh()

bot_state = load_bot_prefs()

def save_bot_prefs():
    os.makedirs(os.path.dirname(BOT_FILE), exist_ok=True)
    json.dump(bot_state, open(BOT_FILE, "w", encoding="utf-8"), indent=1)

def saved_voice_label():
    try:
        return open(SAVED, encoding="utf-8").read().strip()
    except Exception:
        return choices[saved][0] if choices else ""

def apply_bot_voice(bot):
    """The open chat's bot picks the voice. No pick uses the default voice."""
    voice, speed, pitch = bot_prefs.voice_choice(bot_state, bot)
    label = voice or saved_voice_label()
    idx = next((i for i, ch in enumerate(choices) if ch[0] == label), None)
    if idx is None:
        idx = saved
        speed = pitch = None
    use_choice(idx)
    if speed is None:
        speak_state.pop("bot_speed", None)
    else:
        speak_state["bot_speed"] = float(speed)
    if pitch is None:
        speak_state.pop("bot_pitch", None)
    else:
        speak_state["bot_pitch"] = int(pitch)

def log(msg):
    try:
        path = platform.log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass

def fallback_local():
    """Jenny, then any Piper voice, then espeak-ng on Linux."""
    piper = next((c for c in choices if c[1] == "piper" and c[0].startswith("Jenny")), None)
    if piper is None:
        piper = next((c for c in choices if c[1] == "piper"), None)
    if piper:
        return piper[1], piper[2]
    espeak = next((c for c in choices if c[1] == "espeak"), None)
    if espeak:
        return espeak[1], espeak[2]
    return None, None

def stop_all():
    speak_state["token"] += 1
    speak_state["busy_until"] = 0.0
    speak_state["held"] = False
    platform.stop_all_audio()

def piper_job(text, token, wait):
    try:
        kind = speak_state["kind"]
        ref = speak_state["ref"]
        if kind == "grok":
            try:
                if not platform.load_key():
                    raise RuntimeError("no xAI key set")
                pcm = grok_audio(text, ref, tune()["speed"])
                if token != speak_state["token"]:
                    return
                write_pcm_wav(WAV, pcm)
                platform.audio.arm(WAV)
                if speak_state.get("paused"):
                    return
                platform.audio.play(wait)
                return
            except Exception as exc:
                log("Grok voice problem, using a local voice: %r" % (exc,))
                kind, ref = fallback_local()
                if kind is None:
                    return
        if token != speak_state["token"]:
            return
        settings = tune()
        platform.synthesize(kind, ref, text, settings["speed"], settings["pitch"], WAV)
        if token != speak_state["token"]:
            return
        platform.audio.arm(WAV)
        if speak_state.get("paused"):
            return   # paused while the audio was being made: wait for Resume
        platform.audio.play(wait)
    except Exception as exc:
        print("Voice problem:", exc)
        log("Voice problem: %r" % (exc,))
    finally:
        if token == speak_state["token"]:
            speak_state["making"] = False

_auto_spoken = set()

def say(text, wait=False, bot=None, replay=False):
    if text and not grok_store.allow_auto_speech(_auto_spoken, text, replay=replay):
        if not replay:
            reason = "already spoken this session" if grok_store.speech_key(text) else "nothing left to read"
            log(grok_store.skip_log(reason, text))
        return
    apply_bot_voice(bot)
    if text:
        log("speak [%s] [%s] %s" % (bot or "?", speak_state.get("label", "?"), text[:60].replace("\n", " ")))
    stop_all()
    if not text:
        return
    speak_state["paused"] = False   # Back/Next/new reply while paused: play it and leave pause
    flags["pause"] = False
    if speak_state["kind"] == "sapi":
        settings = tune()
        platform.speak_sapi(text, settings["speed"], settings["pitch"], wait)
        return
    speak_state["making"] = True
    tok = speak_state["token"]
    if wait:
        piper_job(text, tok, True)
    else:
        threading.Thread(target=piper_job, args=(text, tok, False), daemon=True).start()

def pause_audio():
    """Pause mid-reply and remember the spot."""
    speak_state["paused"] = True
    if speak_state["kind"] == "sapi":
        platform.pause_sapi()
        return
    if platform.audio.pause():
        speak_state["held"] = True
    elif speak_state["making"]:
        speak_state["held"] = True   # audio still being made; it will wait

def resume_audio():
    """Carry on from the remembered spot."""
    speak_state["paused"] = False
    if speak_state["kind"] == "sapi":
        platform.resume_sapi()
        return
    if not speak_state.pop("held", False):
        return
    if speak_state["making"]:
        return   # job will play it when done
    platform.audio.resume()

def is_speaking():
    if speak_state.get("held") or platform.sapi_is_paused():
        return True   # paused mid-reply still counts as this reply
    if speak_state["kind"] == "sapi":
        return platform.sapi_speaking()
    return speak_state["making"] or platform.audio.is_active()

flags = {"stop": False, "back": False, "skip": False, "pause": False, "quit": False, "play": False}

# Bot names, longest first, so "Vision Design 3.0" wins over "Vision".
BOT_NAMES = sorted(["Moya", "Research Bot", "Grass Hopper", "Time Card", "Design Bot", "Finance Bot",
    "Radar", "Stock Bot", "My Life Bot", "Piper", "Jenny's Bot", "Money Bot", "Remote Access Bot",
    "Cameron", "Vision Design 3.0", "E Watcher", "HA Fixer", "Vision", "Gideon", "Grok Bot",
    "Estimating Bot", "Doc Bot", "Vision Bot", "Appian Bot Vision"], key=len, reverse=True)
import re
TIME_RE = re.compile(r"\b(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*,?\s+)?(?:\w{3,9}\s+\d{1,2},?\s+)?\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|am|pm)?\b")

def remember_names(names):
    changed = False
    fresh_names = []
    for name in names:
        label = " ".join(str(name or "").split())
        if not label:
            continue
        fresh_names.append(label)
        if label not in BOT_NAMES:
            BOT_NAMES.append(label)
            changed = True
    if changed:
        BOT_NAMES.sort(key=len, reverse=True)
    before = set(bot_state["bots"])
    bot_prefs.note_bots(bot_state, fresh_names)
    if set(bot_state["bots"]) != before:
        save_bot_prefs()

def bot_of(reply):
    """The bot named at the start of a stored reply line."""
    return next((name for name in BOT_NAMES if reply.startswith(name + " ")), "")

def announce(reply):
    """'Cameron 6:50 AM Hello there' -> 'Hello there' (no bot name, no time)"""
    text = next((reply[len(name) + 1:] for name in BOT_NAMES if reply.startswith(name + " ")), None)
    if text is None:
        text = reply.partition(" ")[2]
    text = text.strip()
    match = TIME_RE.match(text)            # time at the start
    if match:
        text = text[match.end():].strip()
    text = re.sub(r"^#\d+\s+", "", text)   # Linux chat files mark each line with #seq
    match = re.search(TIME_RE.pattern + r"\s*$", text)   # time at the end
    if match:
        text = text[:match.start()].strip()
    return grok_store.render_speech(text)

_logged_store = False
def chat_snapshot():
    """Visible replies, stable keys, and the open transcript path."""
    global _logged_store
    lines, names, keylists, active = platform.read_snapshot()
    if not _logged_store:
        _logged_store = True
        folder = os.path.dirname(active) if active else (platform.persistence_dir() or "(not found)")
        log("chat folder: %s" % folder)
    remember_names(names)
    kept_lines = []
    kept_keys = []
    for line, keys in zip(lines, keylists):
        if announce(line).strip():
            kept_lines.append(line)
            kept_keys.append(tuple(keys))
    return kept_lines, kept_keys, active

def bot_replies():
    lines, _keys, _active = chat_snapshot()
    return lines

def absorb_current():
    """Mark whatever is in the chat now as already read. Returns those lines."""
    lines, keys, active = chat_snapshot()
    for keyset in keys:
        state["seen"].update(keyset)
    if active is not None:
        state["file_key"] = active
    state["prev_cur"] = list(lines)
    return lines

platform.install_hotkeys(flags)

# ---------- toolbar (rounded, dark, draggable) ----------
platform.hide_console()

BG, PANEL, FG, DIM, ACCENT, RED, KEY = "#1f2430", "#2a3040", "#e8ecf4", "#8a93a6", "#4cc38a", "#ff6b6b", "#ff00fe"

root = tk.Tk()
_window["root"] = root
root.title(APP_TITLE)
platform.apply_icon(root)
root.overrideredirect(True)
root.attributes("-topmost", True)
# Windows punches the magenta key color out so the rounded corners are transparent.
# Linux Tk has no -transparentcolor. Use the bar color instead of leaving magenta corners.
try:
    root.attributes("-transparentcolor", KEY)
    _bar_bg = KEY
except tk.TclError:
    _bar_bg = BG
root.configure(bg=_bar_bg)
sw = root.winfo_screenwidth()
sh = root.winfo_screenheight()

def window_file():
    return os.path.join(platform.config_dir(), "window.json")

def saved_window():
    try:
        data = json.load(open(window_file(), encoding="utf-8"))
        layout = window_layout.normalize_layout(data.get("layout"))
        w, h = window_layout.clamp_size(data["w"], data["h"], layout)
        x, y = window_layout.clamp_origin(data["x"], data["y"], w, h, sw, sh, layout)
        return w, h, x, y, layout
    except Exception:
        w, h = window_layout.DEFAULT_W, window_layout.DEFAULT_H
        return w, h, int(sw - w - sw * 0.10), int(sh - h - sh * 0.05), "horizontal"

window_state = {"layout": "horizontal"}
W, H, OX, OY, window_state["layout"] = saved_window()
root.geometry("%dx%d+%d+%d" % (W, H, OX, OY))

c = tk.Canvas(root, width=W, height=H, bg=_bar_bg, highlightthickness=0)
c.pack(fill="both", expand=True)
def rounded_points(x1, y1, x2, y2, r):
    return [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2, x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1]
shell = c.create_polygon(rounded_points(1, 1, W-1, H-1, 22), smooth=True, fill=BG, outline="#3a4256")

# title + status
title_id = c.create_text(16, 16, text="🔊  " + APP_TITLE, anchor="w", fill=FG, font=("Segoe UI Semibold", 10))
dot = c.create_oval(248, 11, 258, 21, fill=ACCENT, outline="")
stxt = c.create_text(264, 16, text="Watching", anchor="w", fill=DIM, font=("Segoe UI", 9))
status = tk.StringVar(value="Watching")
hold_status = {"text": ""}
update_note = {"text": ""}
update_state = {"result": None}
LABELS = {"Stopped": "Not monitoring", "Paused": "Reading paused"}
btn = {}   # name -> (circle, glyph)
def base_fill(name):
    value = status.get()
    if name == "stop" and value == "Stopped":
        return RED
    if name == "pause" and value == "Paused":
        return "#f5b942"
    return PANEL
def show_status(*_):
    value = status.get()
    c.itemconfig(stxt, text=LABELS.get(value, value), fill=DIM)
    c.itemconfig(dot, fill={"Watching": ACCENT, "Reading": "#5aa9ff", "Paused": "#f5b942", "Stopped": RED, "Update available": ACCENT}.get(value, DIM))
    for name, (circle, glyph) in btn.items():
        c.itemconfig(circle, fill=base_fill(name))
    if "pause" in btn:
        c.itemconfig(btn["pause"][1], fill="#1f2430" if value == "Paused" else FG)
    if "play" in btn:   # green only while monitoring
        c.itemconfig(btn["play"][1], fill=ACCENT if value in ("Watching", "Reading", "Update available") else DIM)
status.trace_add("write", show_status)

# drag the background to move; drag an edge or corner to resize
EDGE = 8
drag = {}
resize = {}
_CURSORS = {
    "n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
    "e": "sb_h_double_arrow", "w": "sb_h_double_arrow",
    "nw": "top_left_corner", "se": "bottom_right_corner",
    "ne": "top_right_corner", "sw": "bottom_left_corner",
}
def edge_at(x, y):
    width = max(c.winfo_width(), 1)
    height = max(c.winfo_height(), 1)
    left, right = x <= EDGE, x >= width - EDGE
    top, bottom = y <= EDGE, y >= height - EDGE
    if top and left:
        return "nw"
    if top and right:
        return "ne"
    if bottom and left:
        return "sw"
    if bottom and right:
        return "se"
    if top:
        return "n"
    if bottom:
        return "s"
    if left:
        return "w"
    if right:
        return "e"
    return ""
def save_window():
    try:
        os.makedirs(platform.config_dir(), exist_ok=True)
        json.dump({"w": root.winfo_width(), "h": root.winfo_height(), "x": root.winfo_x(), "y": root.winfo_y(),
                   "layout": window_state["layout"]},
                  open(window_file(), "w", encoding="utf-8"))
    except Exception:
        pass
def apply_box(x, y, width, height):
    width, height = window_layout.clamp_size(width, height, window_state["layout"])
    if "w" in resize.get("edge", ""):
        x = resize["gx"] + resize["w"] - width
    if "n" in resize.get("edge", ""):
        y = resize["gy"] + resize["h"] - height
    root.geometry("%dx%d+%d+%d" % (width, height, x, y))
def press(e):
    kind = edge_at(e.x, e.y)
    if kind:
        resize.update(edge=kind, x=e.x_root, y=e.y_root, gx=root.winfo_x(), gy=root.winfo_y(),
                      w=root.winfo_width(), h=root.winfo_height())
        drag.clear()
        return
    resize.clear()
    if c.find_withtag("button"):
        if c.find_overlapping(e.x, e.y, e.x, e.y) and set(c.find_overlapping(e.x, e.y, e.x, e.y)) & set(c.find_withtag("button")):
            return
    drag.update(x=e.x, y=e.y)
def move(e):
    if resize:
        dx = e.x_root - resize["x"]
        dy = e.y_root - resize["y"]
        width, height = resize["w"], resize["h"]
        origin_x, origin_y = resize["gx"], resize["gy"]
        if "e" in resize["edge"]:
            width = resize["w"] + dx
        if "s" in resize["edge"]:
            height = resize["h"] + dy
        if "w" in resize["edge"]:
            width = resize["w"] - dx
        if "n" in resize["edge"]:
            height = resize["h"] - dy
        apply_box(origin_x, origin_y, width, height)
        return
    if drag:
        root.geometry("+%d+%d" % (root.winfo_x() + e.x - drag["x"], root.winfo_y() + e.y - drag["y"]))
def hover_edge(e):
    if resize or drag:
        return
    root.configure(cursor=_CURSORS.get(edge_at(e.x, e.y), ""))
def release(_e):
    resize.clear()
    drag.clear()
    root.configure(cursor="")
    save_window()
c.bind("<Button-1>", press)
c.bind("<B1-Motion>", move)
c.bind("<Motion>", hover_edge)
c.bind("<ButtonRelease-1>", release)

# round icon buttons
tip_box = {"win": None}
def hide_tip():
    win = tip_box.get("win")
    if win is not None:
        try:
            win.destroy()
        except Exception:
            pass
        tip_box["win"] = None
def show_tip(event, text):
    hide_tip()
    tip = tk.Toplevel(root)
    tip.overrideredirect(True)
    tip.attributes("-topmost", True)
    tip.configure(bg="#11151c", highlightthickness=1, highlightbackground="#3a4256")
    tk.Label(tip, text=text, bg="#11151c", fg=FG, font=("Segoe UI", 9), padx=8, pady=4).pack()
    tip.update_idletasks()
    x = event.x_root + 12
    y = event.y_root - tip.winfo_height() - 10
    tip.geometry("+%d+%d" % (x, y))
    tip_box["win"] = tip
def icon_button(x, glyph, tip, action, color=FG, y=50, r=15, size=12, name=None):
    circle = c.create_oval(x-r, y-r, x+r, y+r, fill=PANEL, outline="", tags=("button",))
    label = c.create_text(x, y, text=glyph, fill=color, font=("Segoe UI Symbol", size), tags=("button",))
    if name:
        btn[name] = (circle, label)
    def enter(e, circle=circle, tip=tip):
        c.itemconfig(circle, fill="#3a4256")
        show_tip(e, tip)
    def leave(e, circle=circle):
        hide_tip()
        show_status()
    for item in (circle, label):
        def click(e, action=action):
            hide_tip()
            if edge_at(e.x, e.y):
                return
            action()
        c.tag_bind(item, "<Enter>", enter)
        c.tag_bind(item, "<Leave>", leave)
        c.tag_bind(item, "<Button-1>", click)
icon_button(120, "\u23EE", bot_prefs.TOOLBAR_TIPS["back"], lambda: flags.update(back=True), name="back")
icon_button(165, "\u25A0", bot_prefs.TOOLBAR_TIPS["stop"], lambda: flags.update(stop=True), name="stop")
icon_button(210, "\u275A\u275A", bot_prefs.TOOLBAR_TIPS["pause"], lambda: flags.update(pause=True), name="pause")
icon_button(255, "\u25B6", bot_prefs.TOOLBAR_TIPS["play"], lambda: flags.update(pause=False, play=True), ACCENT, name="play")
show_status()
icon_button(300, "\u23ED", bot_prefs.TOOLBAR_TIPS["next"], lambda: flags.update(skip=True), name="next")
icon_button(W-50, "\u2699", bot_prefs.TOOLBAR_TIPS["gear"], lambda: open_tuner(), y=17, r=11, size=10, name="gear")
icon_button(W-22, "\u23FB", bot_prefs.TOOLBAR_TIPS["power"], lambda: flags.update(quit=True), RED, y=17, r=11, size=10, name="power")

def relayout(width, height):
    width, height = window_layout.clamp_size(width, height, window_state["layout"])
    c.configure(width=width, height=height)
    c.coords(shell, *rounded_points(1, 1, max(2, width - 1), max(2, height - 1), min(22, width // 4, height // 4)))
    plan = window_layout.arrange(width, height, window_state["layout"])
    c.coords(title_id, *plan["title"])
    sx, sy = plan["status"]
    c.coords(dot, sx, sy - 5, sx + 10, sy + 5)
    c.coords(stxt, sx + 14, sy)
    for name, x, y, radius in plan["buttons"]:
        circle, glyph = btn[name]
        c.coords(circle, x - radius, y - radius, x + radius, y + radius)
        c.coords(glyph, x, y)
def on_configure(event):
    if event.widget is not root:
        return
    relayout(event.width, event.height)
root.bind("<Configure>", on_configure)
relayout(W, H)

tuner = {"win": None}
def open_tuner():
    if tuner["win"] is not None:
        tuner["win"].destroy()
        tuner["win"] = None
        return
    default_label = saved_voice_label() or (choices[saved][0] if choices else "")
    settings = voice_tune(default_label)
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg=BG, highlightthickness=1, highlightbackground="#3a4256")
    tk.Label(win, text=APP_TITLE, bg=BG, fg=FG, font=("Segoe UI Semibold", 9)).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 2))
    tk.Label(win, text="Toolbar", bg=BG, fg=DIM, font=("Segoe UI", 9), width=8, anchor="w").grid(row=3, column=0, padx=(10, 0), sticky="w")
    layout_row = tk.Frame(win, bg=BG)
    layout_row.grid(row=3, column=1, sticky="w", padx=(0, 10))
    layout_var = tk.StringVar(value=window_state["layout"])
    def choose_layout():
        window_state["layout"] = window_layout.normalize_layout(layout_var.get())
        width, height = window_layout.clamp_size(root.winfo_width(), root.winfo_height(), window_state["layout"])
        root.geometry("%dx%d+%d+%d" % (width, height, root.winfo_x(), root.winfo_y()))
        relayout(width, height)
        save_window()
    for value, caption in (("horizontal", "Horizontal"), ("vertical", "Vertical")):
        tk.Radiobutton(layout_row, text=caption, variable=layout_var, value=value, command=choose_layout,
                       bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
    tk.Label(win, text="Default", bg=BG, fg=DIM, font=("Segoe UI", 9), width=8, anchor="w").grid(row=4, column=0, padx=(10, 0), pady=(4, 2))
    vb = tk.Button(win, text="\U0001F3A4 " + default_label + "  \u25BE", bg=PANEL, fg=FG, activebackground="#3a4256", activeforeground=FG,
                   relief="flat", bd=0, padx=10, pady=3, font=("Segoe UI", 9), anchor="w", width=28)
    vb.configure(command=lambda: menu.tk_popup(vb.winfo_rootx(), vb.winfo_rooty() + vb.winfo_height()))
    vb.grid(row=4, column=1, padx=(0, 10), pady=(4, 2), sticky="w")
    def slider(row, label, lo, hi, res, val, key):
        tk.Label(win, text=label, bg=BG, fg=DIM, font=("Segoe UI", 9), width=8, anchor="w").grid(row=row, column=0, padx=(10, 0))
        sc = tk.Scale(win, from_=lo, to=hi, resolution=res, orient="horizontal", length=220,
                      bg=BG, fg=FG, troughcolor=PANEL, highlightthickness=0, bd=0,
                      activebackground=ACCENT, sliderrelief="flat", font=("Segoe UI", 8))
        sc.set(val)
        sc.grid(row=row, column=1, padx=(0, 10))
        def changed(value, key=key):
            voice_tune(default_label)[key] = float(value) if key == "speed" else int(float(value))
            save_tune()
        sc.configure(command=changed)
    slider(1, "Speed", 0.5, 2.0, 0.1, settings["speed"], "speed")
    slider(2, "Pitch", -10, 10, 1, settings["pitch"], "pitch")
    new_var = tk.BooleanVar(value=bool(bot_state.get("new_bots", True)))
    read_vars = {}
    def on_new():
        bot_state["new_bots"] = bool(new_var.get())
        save_bot_prefs()
        for name, var in read_vars.items():
            row = bot_state["bots"].get(name) or {}
            if "read" not in row:
                var.set(bot_prefs.allows_auto(bot_state, name))
    tk.Checkbutton(win, text="New bots on by default", variable=new_var, command=on_new,
                   bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                   font=("Segoe UI", 9), anchor="w").grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 0))
    tk.Label(win, text="Bots", bg=BG, fg=DIM, font=("Segoe UI", 9)).grid(row=7, column=0, columnspan=2, sticky="w", padx=10)
    holder = tk.Frame(win, bg=BG)
    holder.grid(row=8, column=0, columnspan=2, sticky="ew", padx=8)
    box = tk.Canvas(holder, bg=BG, highlightthickness=0, height=160, width=420)
    box.pack(side="left", fill="both")
    inner = tk.Frame(box, bg=BG)
    box.create_window((0, 0), window=inner, anchor="nw")
    def fit(_event=None):
        box.configure(scrollregion=box.bbox("all"))
    inner.bind("<Configure>", fit)
    names = sorted(bot_state["bots"])
    if not names:
        tk.Label(inner, text="Bots show up here after a chat is seen.", bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(anchor="w", padx=4, pady=4)
    voice_labels = ["Default voice"] + [ch[0] for ch in choices]
    for name in names:
        row = bot_state["bots"].setdefault(name, {})
        block = tk.Frame(inner, bg=BG)
        block.pack(fill="x", pady=3)
        read_var = tk.BooleanVar(value=bot_prefs.allows_auto(bot_state, name))
        read_vars[name] = read_var
        def on_read(name=name, var=read_var):
            bot_state["bots"].setdefault(name, {})["read"] = bool(var.get())
            save_bot_prefs()
        tk.Checkbutton(block, text=name, variable=read_var, command=on_read,
                       bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 9), anchor="w").pack(anchor="w")
        picked = (row.get("voice") or "").strip() or "Default voice"
        voice_btn = tk.Button(block, text=picked + "  \u25BE", bg=PANEL, fg=FG, activebackground="#3a4256", activeforeground=FG,
                               relief="flat", bd=0, padx=8, pady=2, font=("Segoe UI", 8), anchor="w")
        menu_b = tk.Menu(win, tearoff=0, bg=PANEL, fg=FG, activebackground="#3a4256", activeforeground=FG, font=("Segoe UI", 8))
        def choose(label, name=name, button=voice_btn):
            stored = "" if label == "Default voice" else label
            bot_state["bots"].setdefault(name, {})["voice"] = stored
            save_bot_prefs()
            button.configure(text=(stored or "Default voice") + "  \u25BE")
        for label in voice_labels:
            menu_b.add_command(label=label, command=lambda label=label: choose(label))
        voice_btn.configure(command=lambda menu_b=menu_b, voice_btn=voice_btn: menu_b.tk_popup(voice_btn.winfo_rootx(), voice_btn.winfo_rooty() + voice_btn.winfo_height()))
        voice_btn.pack(anchor="w", padx=18)
        speeds = tk.Frame(block, bg=BG)
        speeds.pack(fill="x", padx=18)
        base = voice_tune(picked if picked != "Default voice" else default_label)
        for key, lo, hi, res, caption in (("speed", 0.5, 2.0, 0.1, "Speed"), ("pitch", -10, 10, 1, "Pitch")):
            tk.Label(speeds, text=caption, bg=BG, fg=DIM, font=("Segoe UI", 8), width=6, anchor="w").pack(side="left")
            start = row.get(key)
            if not isinstance(start, (int, float)):
                start = base[key]
            sc = tk.Scale(speeds, from_=lo, to=hi, resolution=res, orient="horizontal", length=120,
                          bg=BG, fg=FG, troughcolor=PANEL, highlightthickness=0, bd=0,
                          activebackground=ACCENT, sliderrelief="flat", font=("Segoe UI", 7))
            sc.set(start)
            def changed(value, name=name, key=key):
                number = float(value) if key == "speed" else int(float(value))
                bot_state["bots"].setdefault(name, {})[key] = number
                save_bot_prefs()
            sc.configure(command=changed)
            sc.pack(side="left")
    tk.Label(win, text="Unchecked bots are not read aloud. Back, Next, and Play still speak them.",
             bg=BG, fg=DIM, font=("Segoe UI", 8), wraplength=420, justify="left").grid(row=9, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 0))
    update_row = tk.Frame(win, bg=BG)
    update_row.grid(row=10, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 0))
    update_line = tk.Label(update_row, text="", bg=BG, fg=DIM, font=("Segoe UI", 8))
    update_go = tk.Button(update_row, text="Update", bg=ACCENT, fg="white", activebackground="#3a4256", activeforeground=FG,
                          relief="flat", bd=0, padx=8, pady=2, font=("Segoe UI", 8))
    update_busy = {"on": False}

    def paint_update(result):
        update_busy["on"] = False
        update_state["result"] = result
        try:
            if not update_line.winfo_exists():
                return
        except Exception:
            return
        update_line.configure(text=result.get("message") or "")
        if result.get("available"):
            update_note["text"] = "Update available"
            if not update_go.winfo_ismapped():
                update_go.pack(side="left", padx=(8, 0))
        else:
            if result.get("ok"):
                update_note["text"] = ""
            update_go.pack_forget()

    def check_updates():
        if update_busy["on"]:
            return
        update_busy["on"] = True
        update_line.configure(text="Checking...")
        update_go.pack_forget()

        def work():
            try:
                result = updates.check(VERSION, urllib.request.urlopen)
                updates.write_state(os.path.join(platform.config_dir(), "update-check.json"), time.time(), result)
            except Exception as exc:
                log("update check: %r" % (exc,))
                result = {"ok": False, "available": False, "message": "Could not check for updates."}
            root.after(0, lambda result=result: paint_update(result))

        threading.Thread(target=work, name="update-check", daemon=True).start()

    def install_update():
        result = update_state.get("result") or {}
        if update_busy["on"] or not result.get("available"):
            return
        update_busy["on"] = True
        update_line.configure(text="Downloading update...")
        update_go.configure(state="disabled")

        def work():
            try:
                updates.apply(
                    result, sys.platform, os.getpid(), sys.executable, bool(getattr(sys, "frozen", False)),
                    platform.config_dir(), urllib.request.urlopen, platform.log_path())
            except Exception as exc:
                log("update install: %r" % (exc,))
                def failed():
                    update_busy["on"] = False
                    try:
                        update_line.configure(text="Update did not finish.")
                        update_go.configure(state="normal")
                    except Exception:
                        pass
                root.after(0, failed)
                return
            # The helper waits for this process to leave, then swaps or reinstalls.
            root.after(0, lambda: flags.update(quit=True))

        threading.Thread(target=work, name="update-install", daemon=True).start()

    update_go.configure(command=install_update)
    tk.Button(update_row, text="Check for updates", command=check_updates, bg=PANEL, fg=FG,
              activebackground="#3a4256", activeforeground=FG, relief="flat", bd=0, padx=8, pady=2,
              font=("Segoe UI", 8)).pack(side="left")
    update_line.pack(side="left", padx=(8, 0))
    remembered = update_state.get("result")
    if remembered:
        paint_update(remembered)
    bar2 = tk.Frame(win, bg=BG)
    bar2.grid(row=11, column=0, columnspan=2, pady=(6, 8))
    def reset():
        tune_all[default_label] = {"speed": 1.0, "pitch": 0}
        save_tune()
        win.destroy()
        tuner["win"] = None
        open_tuner()
    for txt, cmd in (("\u25B6 Test", lambda: say("This is how I sound now.", replay=True)), ("Reset", reset), ("Done", lambda: (hide_tip(), win.destroy(), tuner.update(win=None)))):
        tk.Button(bar2, text=txt, command=cmd, bg=PANEL, fg=FG, activebackground="#3a4256", activeforeground=FG,
                  relief="flat", bd=0, padx=10, pady=3, font=("Segoe UI", 9)).pack(side="left", padx=4)
    win.update_idletasks()
    win.geometry(f"+{root.winfo_x() + W - win.winfo_width()}+{max(0, root.winfo_y() - win.winfo_height() - 8)}")
    tuner["win"] = win

# voice switcher
short = [ch[0] for ch in choices]
def set_voice(i):
    use_choice(i)
    path = platform.saved_voice_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(short[i])
    if tuner["win"] is not None:   # refresh the settings panel for the new voice
        tuner["win"].destroy()
        tuner["win"] = None
        open_tuner()
menu = tk.Menu(root, tearoff=0, bg=PANEL, fg=FG, activebackground="#3a4256", activeforeground=FG, font=("Segoe UI", 9))
def key_dialog():
    win = tk.Toplevel(root)
    win.title("xAI API key")
    win.configure(bg=PANEL)
    win.attributes("-topmost", True)
    tk.Label(win, text=platform.key_help(),
             bg=PANEL, fg=FG, font=("Segoe UI", 9), justify="left").pack(padx=12, pady=(10, 6), anchor="w")
    entry = tk.Entry(win, show="\u2022", width=44, bg="#11151c", fg=FG, insertbackground=FG, relief="flat")
    entry.pack(padx=12, pady=4)
    entry.focus_set()
    def ok():
        key = entry.get().strip()
        if key:
            try:
                platform.save_key(key)
            except Exception as exc:
                log("could not save the xAI key: %r" % (exc,))
                return
            gi = next((i for i, ch in enumerate(choices) if ch[1] == "grok"), None)
            if gi is not None:
                set_voice(gi)
        win.destroy()
    tk.Button(win, text="Save", command=ok, bg=ACCENT, fg="white", relief="flat", padx=14).pack(pady=(6, 10))
    win.bind("<Return>", lambda ev: ok())

def fill_voice_menu():
    menu.delete(0, "end")
    for i, n in enumerate(short):
        menu.add_command(label=n, command=lambda i=i: set_voice(i))
    menu.add_separator()
    menu.add_command(label="\u2795  Get More Voices...", command=platform.open_more_voices)
    menu.add_command(label="\U0001F511  Set xAI API key...", command=key_dialog)

def refresh_downloaded_voices():
    """Rebuild the picker after Piper voices land, and start on Jenny if unset."""
    global saved
    fresh = platform.voice_choices()
    chief = chief_name()
    voice_id, _speed = grok_store.chief_voice(platform.persistence_dir(), chief)
    if voice_id:
        fresh.insert(0, ("%s's voice (Grok)" % chief, "grok", voice_id))
    if not fresh:
        fresh.append(("English (espeak-ng)", "espeak", "en"))
    choices[:] = fresh
    short[:] = [ch[0] for ch in choices]
    saved = piper_setup.preferred_index(short, saved_voice_label())
    use_choice(saved)
    fill_voice_menu()
    if tuner["win"] is not None:
        tuner["win"].destroy()
        tuner["win"] = None
        open_tuner()

def download_piper_voices():
    def progress(message):
        hold_status["text"] = message
    try:
        ready = piper_setup.ensure(platform.piper_dir(), sys.platform, progress)
    except Exception as exc:
        log("piper download: %r" % (exc,))
        ready = False
    def finish():
        if ready:
            refresh_downloaded_voices()
            hold_status["text"] = ""
        else:
            hold_status["text"] = "Piper voices unavailable. Using built-in voices."
            root.after(5000, lambda: hold_status.update(text=""))
    root.after(0, finish)

fill_voice_menu()

# ---------- watcher loop ----------
# Replies already on screen at launch are history. Only a reply that appears
# after this baseline is read aloud. Back and Next can still walk the history.
_lines, _keys, _active = chat_snapshot()
_seen = set()
grok_store.mark_seen(_seen, _keys)
try:
    # Other chats are history too. A reply that shows up later is the only new one.
    grok_store.mark_seen(_seen, platform.all_reply_keys())
except Exception:
    pass
state = {"seen": _seen, "history": list(_lines), "pos": None, "queue": [], "paused": False, "stopped": False, "next": 0,
         "file_key": _active, "prev_cur": list(_lines), "explained": set()}

def tick():
    if flags["quit"]:
        save_window()
        say("")
        _instance.release()
        root.destroy()
        return
    if flags["stop"]:            # Stop: end this reply and stop watching until Play
        flags["stop"] = False
        state["queue"].clear()
        state["stopped"] = True
        flags["pause"] = False
        state["paused"] = False
        say("")
    def use_open_chat():
        """Point history at the chat on screen. Empty history means we are not sure."""
        cur, keys, active = chat_snapshot()
        if active is None and not cur:
            # Back stays quiet. Keep file_key so a later reply in that chat is still read.
            state["history"] = []
            state["pos"] = None
            state["queue"].clear()
            state["prev_cur"] = []
            return False
        if active is not None and active != state.get("file_key"):
            grok_store.mark_seen(state["seen"], keys)
            state["history"] = list(cur)
            state["file_key"] = active
            state["prev_cur"] = list(cur)
            state["queue"].clear()
            state["pos"] = None
            return True
        if active is None:
            state["history"] = list(cur)
            state["file_key"] = None
            state["pos"] = None
            return bool(cur)
        return True

    manual = None
    if flags["play"]:
        flags["play"] = False
        resuming = state["paused"]
        if not resuming and not use_open_chat():
            say("")
        elif state["stopped"]:     # back to watching; anything already on screen is skipped
            state["stopped"] = False
            state["history"] = absorb_current()
        history = state["history"]
        if history and not resuming:
            shown = history[-1] if state["pos"] is None else history[state["pos"]]
            if not bot_prefs.allows_auto(bot_state, bot_of(shown)):
                manual = shown
    if flags["back"]:
        flags["back"] = False
        # Re-read before speaking. A switch replaces history with that bot's
        # lines, and the first Back plays the latest one, even if it arrived
        # before the switch. An unknown chat stays silent.
        if not use_open_chat():
            say("")
        else:
            history = state["history"]
            if history:
                state["pos"] = len(history) - 1 if state["pos"] is None else max(0, state["pos"] - 1)
                state["queue"].clear()
                say(announce(history[state["pos"]]), bot=bot_of(history[state["pos"]]), replay=True)
            else:
                say("")
    if flags["skip"]:   # Next
        flags["skip"] = False
        use_open_chat()
        history = state["history"]
        if state["pos"] is not None and state["pos"] < len(history) - 1:
            state["pos"] += 1          # step forward through history
            state["queue"].clear()
            say(announce(history[state["pos"]]), bot=bot_of(history[state["pos"]]), replay=True)
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
            absorb_current()    # skip what came in while paused
    if manual:
        say(announce(manual), bot=bot_of(manual), replay=True)
    if not state["paused"] and not state["stopped"] and time.time() >= state["next"]:
        state["next"] = time.time() + 1
        try:
            cur, names, keys, active, skipped = platform.watch_snapshot(state["seen"], state.get("file_key"))
            remember_names(names)
            kept_lines = []
            kept_keys = []
            for line, keyset in zip(cur, keys):
                if announce(line).strip():
                    kept_lines.append(line)
                    kept_keys.append(tuple(keyset))
                elif not any(key in state["seen"] for key in keyset):
                    token = tuple(keyset)
                    if token not in state["explained"]:
                        state["explained"].add(token)
                        log(grok_store.skip_log("nothing left to read", line))
            cur, keys = kept_lines, kept_keys
            for keyset, reason, preview in skipped:
                token = tuple(keyset)
                if token not in state["explained"]:
                    state["explained"].add(token)
                    log(grok_store.skip_log(reason, preview))
            seen = state["seen"]
            if active is not None:
                # A different chat that is still on disk replaces history and
                # is not read aloud. The same file, or the first file we can
                # lock onto, speaks replies that arrived after launch.
                previous = state.get("file_key")
                if previous and not os.path.exists(previous):
                    previous = None
                    state["history"] = []
                    state["file_key"] = None
                moved = previous and active != previous
                if moved:
                    state["file_key"] = active
                    grok_store.mark_seen(seen, keys)
                    state["history"] = list(cur)
                    state["prev_cur"] = list(cur)
                    state["queue"].clear()
                    state["pos"] = None
                else:
                    fresh = grok_store.unseen_lines(seen, cur, keys)
                    if not state.get("file_key"):
                        state["history"] = list(cur)
                        state["prev_cur"] = list(cur)
                        state["pos"] = None
                    else:
                        for line in fresh:
                            state["history"].append(line)
                            state["pos"] = None
                    state["file_key"] = active
                    for line in fresh:
                        state["queue"].append(line)
            elif cur:
                known = [i for i, reply in enumerate(cur) if reply in seen]
                prev = state.get("prev_cur", [])
                if grok_store.launch_is_baseline(seen, cur, prev):
                    # The window was not ready at launch. This first view is history.
                    seen.update(cur)
                    state["history"] = list(cur)
                    state["prev_cur"] = list(cur)
                    state["queue"].clear()
                    state["pos"] = None
                    known = list(range(len(cur)))
                    prev = list(cur)
                if cur:
                    state["prev_cur"] = list(cur)   # keep the last real view while a chat loads
                def who(reply):
                    return next((name for name in BOT_NAMES if reply.startswith(name + " ")), reply.partition(" ")[0])
                switched = bool(cur) and not grok_store.launch_is_baseline(seen, cur, prev) and (
                    (prev and not set(prev) & set(cur))                 # nothing in common with the last chat
                    or (prev and who(prev[-1]) != who(cur[-1]))         # a different bot is on screen
                    or (not known and (prev or len(cur) > 1)))
                if switched:
                    # new bot or chat: cut off the old read now, start at the bottom, all above counts as read
                    bottom = cur[-1]
                    already = bottom in seen or any(key in seen for key in (keys[-1] if keys else []))
                    seen.update(cur)
                    for keyset in keys:
                        seen.update(keyset)
                    state["history"] = list(cur)
                    state["queue"].clear()
                    # A message already spoken this session stays quiet. Back steps up from here.
                    state["pos"] = len(cur) - 1
                    if not already and bot_prefs.allows_auto(bot_state, bot_of(bottom)):
                        say(announce(bottom), bot=bot_of(bottom))
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
            elif state.get("file_key") and not os.path.exists(state["file_key"]):
                state["file_key"] = None
        except Exception as exc:
            message = repr(exc)
            if state.get("watch_error") != message:
                state["watch_error"] = message
                log("watch problem: %s" % message)
    speaking = is_speaking()
    if state["queue"] and not speaking and not state["paused"] and not state["stopped"]:
        pending = state["queue"].pop(0)
        who = bot_of(pending)
        if bot_prefs.allows_auto(bot_state, who):
            say(announce(pending), bot=who)
            speaking = True
    if state["stopped"] and not speaking:
        new = "Stopped"
    elif state["paused"]:
        new = "Paused"
    else:
        new = "Reading" if speaking else "Watching"
    if hold_status["text"]:
        shown = hold_status["text"]
    elif new == "Watching" and update_note["text"]:
        shown = update_note["text"]
    else:
        shown = new
    if status.get() != shown:
        status.set(shown)
    root.after(200, tick)

def quiet_update_check():
    """Ask GitHub at most once a day. A newer release is only a note, never an install."""
    path = os.path.join(platform.config_dir(), "update-check.json")
    now = time.time()
    action, note = updates.launch_note(VERSION, updates.read_state(path), now)
    if action == "clear":
        try:
            updates.write_state(path, now, {"latest": VERSION, "available": False})
        except Exception:
            pass
        return
    if action == "skip":
        if note:
            root.after(0, lambda: update_note.update(text=note))
        return
    result = None
    try:
        result = updates.check(VERSION, urllib.request.urlopen)
    except Exception as exc:
        log("update check: %r" % (exc,))
    try:
        if not (result and result.get("ok")):
            previous = updates.read_state(path)
            result = {"latest": previous["latest"], "available": previous["available"]}
        updates.write_state(path, now, result)
    except Exception:
        pass

    def show(result=result):
        if result and result.get("ok"):
            update_state["result"] = result
            update_note["text"] = "Update available" if result.get("available") else ""
        elif result and result.get("available") and updates.newer(VERSION, result.get("latest")):
            update_note["text"] = "Update available"
    root.after(0, show)

if os.environ.get("GROKBOT_VOICE_SELFTEST") == "1":
    root.update_idletasks()
    root.update()
    root.destroy()
else:
    try:
        updates.remove_old_updater(platform.config_dir())
    except Exception:
        pass
    threading.Thread(target=download_piper_voices, name="piper-setup", daemon=True).start()
    threading.Thread(target=quiet_update_check, name="update-check", daemon=True).start()
    root.after(200, tick)
    root.mainloop()
