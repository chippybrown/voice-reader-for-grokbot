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

import grok_store
from audio_util import write_chime, write_pcm_wav

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

def tune():   # current voice's {"speed": 0.5..2.0, "pitch": -10..10}
    saved = tune_all.setdefault(speak_state.get("label", ""), {})
    saved.setdefault("speed", 1.0)
    saved.setdefault("pitch", 0)
    return saved

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
saved = next((i for i, ch in enumerate(choices) if ch[0] == saved_label), 0)
use_choice(saved)

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

def say(text, wait=False):
    if text:
        log("speak [%s] %s" % (speak_state.get("label", "?"), text[:60].replace("\n", " ")))
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
    for name in names:
        if name and name not in BOT_NAMES:
            BOT_NAMES.append(name)
            changed = True
    if changed:
        BOT_NAMES.sort(key=len, reverse=True)

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
    return text

_logged_store = False
def bot_replies():
    global _logged_store
    if not _logged_store:
        _logged_store = True
        log("chat folder: %s" % (platform.persistence_dir() or "(not found)"))
    lines, names = platform.read_chat()
    remember_names(names)
    return [line for line in lines if announce(line).strip()]

platform.install_hotkeys(flags)

# ---------- toolbar (rounded, dark, draggable) ----------
platform.hide_console()

BG, PANEL, FG, DIM, ACCENT, RED, KEY = "#1f2430", "#2a3040", "#e8ecf4", "#8a93a6", "#4cc38a", "#ff6b6b", "#ff00fe"
W, H = 300, 74
root = tk.Tk()
root.title("Grokbot Voice")
platform.apply_icon(root)
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
    pts = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2, x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)
rounded(1, 1, W-1, H-1, 22, fill=BG, outline="#3a4256")

# title + status
c.create_text(16, 16, text="🔊  Grokbot Voice", anchor="w", fill=FG, font=("Segoe UI Semibold", 10))
dot = c.create_oval(138, 11, 148, 21, fill=ACCENT, outline="")
stxt = c.create_text(152, 16, text="Watching", anchor="w", fill=DIM, font=("Segoe UI", 9))
# A small microphone with a slash, shown only while Grok Bot's mic is muted.
mic_parts = [
    c.create_oval(222, 9, 230, 17, outline=RED, width=2, state="hidden"),
    c.create_line(226, 17, 226, 21, fill=RED, width=2, state="hidden"),
    c.create_line(222, 20, 230, 20, fill=RED, width=2, state="hidden"),
    c.create_line(220, 20, 232, 8, fill=RED, width=2, state="hidden"),
]
status = tk.StringVar(value="Watching")
LABELS = {"Stopped": "Not monitoring", "Paused": "Reading paused"}
mic = {"muted": False, "sweep": 0.0}
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
    if mic["muted"]:
        c.itemconfig(stxt, text="Mic muted", fill=RED)
        c.itemconfig(dot, fill=RED)
        for part in mic_parts:
            c.itemconfig(part, state="normal")
    else:
        c.itemconfig(stxt, text=LABELS.get(value, value), fill=DIM)
        c.itemconfig(dot, fill={"Watching": ACCENT, "Reading": "#5aa9ff", "Paused": "#f5b942", "Stopped": RED}.get(value, DIM))
        for part in mic_parts:
            c.itemconfig(part, state="hidden")
    for name, (circle, glyph) in btn.items():
        c.itemconfig(circle, fill=base_fill(name))
    if "pause" in btn:
        c.itemconfig(btn["pause"][1], fill="#1f2430" if value == "Paused" else FG)
    if "play" in btn:   # green only while monitoring
        c.itemconfig(btn["play"][1], fill=ACCENT if value in ("Watching", "Reading") else DIM)
status.trace_add("write", show_status)

# drag anywhere on the background
drag = {}
def press(e):
    drag.update(x=e.x, y=e.y)
def move(e):
    root.geometry(f"+{root.winfo_x() + e.x - drag['x']}+{root.winfo_y() + e.y - drag['y']}")
c.bind("<Button-1>", press)
c.bind("<B1-Motion>", move)

# round icon buttons
def icon_button(x, glyph, tip, action, color=FG, y=50, r=15, size=12, name=None):
    circle = c.create_oval(x-r, y-r, x+r, y+r, fill=PANEL, outline="")
    label = c.create_text(x, y, text=glyph, fill=color, font=("Segoe UI Symbol", size))
    if name:
        btn[name] = (circle, label)
    for item in (circle, label):
        c.tag_bind(item, "<Enter>", lambda e, circle=circle, tip=tip: (c.itemconfig(circle, fill="#3a4256"), c.itemconfig(stxt, text=tip)))
        c.tag_bind(item, "<Leave>", lambda e, circle=circle: show_status())
        c.tag_bind(item, "<Button-1>", lambda e, action=action: action())
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
        tuner["win"].destroy()
        tuner["win"] = None
        return
    settings = tune()
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
        def changed(value):
            tune()[key] = float(value) if key == "speed" else int(float(value))
            save_tune()
        sc.configure(command=changed)
    slider(1, "Speed", 0.5, 2.0, 0.1, settings["speed"], "speed")
    slider(2, "Pitch", -10, 10, 1, settings["pitch"], "pitch")
    cmd_var = tk.BooleanVar(value=commands_enabled())
    def on_commands():
        enabled = bool(cmd_var.get())
        save_commands_enabled(enabled)
        if enabled:
            start_voice_commands()
        else:
            stop_voice_commands()
    tk.Checkbutton(win, text="Voice commands (Moya mute / Moya wake)", variable=cmd_var, command=on_commands,
                   bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                   font=("Segoe UI", 9), anchor="w").grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 0))
    bar2 = tk.Frame(win, bg=BG)
    bar2.grid(row=5, column=0, columnspan=2, pady=(6, 8))
    def reset():
        tune_all[speak_state["label"]] = {"speed": 1.0, "pitch": 0}
        save_tune()
        win.destroy()
        tuner["win"] = None
        open_tuner()
    for txt, cmd in (("\u25B6 Test", lambda: say("This is how I sound now.")), ("Reset", reset), ("Done", lambda: (win.destroy(), tuner.update(win=None)))):
        tk.Button(bar2, text=txt, command=cmd, bg=PANEL, fg=FG, activebackground="#3a4256", activeforeground=FG,
                  relief="flat", bd=0, padx=10, pady=3, font=("Segoe UI", 9)).pack(side="left", padx=4)
    win.update_idletasks()
    win.geometry(f"+{root.winfo_x() + W - win.winfo_width()}+{root.winfo_y() - win.winfo_height() - 8}")
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
for i, n in enumerate(short):
    menu.add_command(label=n, command=lambda i=i: set_voice(i))
menu.add_separator()
menu.add_command(label="\u2795  Get More Voices...", command=platform.open_more_voices)
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
menu.add_command(label="\U0001F511  Set xAI API key...", command=key_dialog)

# ---------- watcher loop ----------
_first = bot_replies()
state = {"seen": set(_first), "history": list(_first), "pos": None, "queue": [], "paused": False, "stopped": False, "next": 0}

def commands_path():
    return os.path.join(platform.config_dir(), "voice-commands.json")

def commands_enabled():
    try:
        return bool(json.load(open(commands_path(), encoding="utf-8")).get("enabled", True))
    except Exception:
        return True

def save_commands_enabled(on):
    os.makedirs(platform.config_dir(), exist_ok=True)
    json.dump({"enabled": bool(on)}, open(commands_path(), "w", encoding="utf-8"))

def ensure_chimes():
    down = platform.wav_path("chime-mute")
    up = platform.wav_path("chime-wake")
    if not os.path.isfile(down):
        write_chime(down, [392])
    if not os.path.isfile(up):
        write_chime(up, [523, 784], ms=110)
    return down, up

def apply_mic(muted):
    """Spoken Moya mute / Moya wake. Reading is left alone."""
    changed = mic["muted"] != muted
    mic["muted"] = muted
    mic["sweep"] = time.time() + 1
    try:
        platform.set_grok_mic_muted(muted)
    except Exception as exc:
        log("mic mute problem: %r" % (exc,))
    if changed:
        try:
            down, up = ensure_chimes()
            platform.play_chime(down if muted else up)
        except Exception as exc:
            log("chime problem: %r" % (exc,))
    show_status()

listener_box = {"obj": None}

def on_voice_command(action):
    root.after(0, lambda: apply_mic(action == "mute"))

def start_voice_commands():
    if listener_box.get("obj"):
        listener_box["obj"].start()
        return
    try:
        from voice_listener import VoiceListener
    except Exception as exc:
        log("voice commands unavailable: %r" % (exc,))
        return
    listener_box["obj"] = VoiceListener(platform.config_dir(), on_voice_command, is_speaking, log)
    listener_box["obj"].start()

def stop_voice_commands():
    obj = listener_box.get("obj")
    if obj:
        obj.stop()
    if mic["muted"]:
        mic["muted"] = False
        try:
            platform.set_grok_mic_muted(False)
        except Exception as exc:
            log("mic unmute problem: %r" % (exc,))
        show_status()

def tick():
    if flags["quit"]:
        if mic["muted"]:
            try:
                platform.set_grok_mic_muted(False)
            except Exception:
                pass
        stop_obj = listener_box.get("obj")
        if stop_obj:
            stop_obj.stop()
        say("")
        root.destroy()
        return
    if mic["muted"] and time.time() >= mic["sweep"]:
        mic["sweep"] = time.time() + 1
        try:
            platform.set_grok_mic_muted(True)
        except Exception:
            pass
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
        history = state["history"]
        if history:
            state["pos"] = len(history) - 1 if state["pos"] is None else max(0, state["pos"] - 1)
            state["queue"].clear()
            say(announce(history[state["pos"]]))
    if flags["skip"]:   # Next
        flags["skip"] = False
        history = state["history"]
        if state["pos"] is not None and state["pos"] < len(history) - 1:
            state["pos"] += 1          # step forward through history
            state["queue"].clear()
            say(announce(history[state["pos"]]))
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
            known = [i for i, reply in enumerate(cur) if reply in seen]
            prev = state.get("prev_cur", [])
            if cur:
                state["prev_cur"] = list(cur)   # keep the last real view while a chat loads
            def who(reply):
                return next((name for name in BOT_NAMES if reply.startswith(name + " ")), reply.partition(" ")[0])
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

if commands_enabled():
    start_voice_commands()
root.after(200, tick)
root.mainloop()
