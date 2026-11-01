# Grok Voice (automatic) for the Grok Bot desktop app on Windows.
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
    voice.Speak("", ASYNC | PURGE)
    winsound.PlaySound(None, 0)

def piper_job(text, token, wait):
    try:
        ref = speak_state["ref"]
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
        speak_state["busy_until"] = time.time() + secs
        winsound.PlaySound(WAV, winsound.SND_FILENAME | (0 if wait else winsound.SND_ASYNC))
    except Exception as e:
        print("Piper problem:", e)
    finally:
        if token == speak_state["token"]:
            speak_state["making"] = False

def say(text, wait=False):
    stop_all()
    if not text:
        return
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

def is_speaking():
    if speak_state["kind"] == "sapi":
        return voice.Status.RunningState == 2
    return speak_state["making"] or time.time() < speak_state["busy_until"]

flags = {"stop": False, "back": False, "skip": False, "pause": False, "quit": False}
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
            found.append(name)
    return found

# ---------- toolbar (rounded, dark, draggable) ----------
import ctypes
try:  # hide the black console window if one opened
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)
except Exception:
    pass

BG, PANEL, FG, DIM, ACCENT, RED, KEY = "#1f2430", "#2a3040", "#e8ecf4", "#8a93a6", "#4cc38a", "#ff6b6b", "#ff00fe"
W, H = 420, 74
root = tk.Tk()
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
c.create_text(16, 16, text="🔊  Grok Voice", anchor="w", fill=FG, font=("Segoe UI Semibold", 10))
dot = c.create_oval(W//2-40, 11, W//2-30, 21, fill=ACCENT, outline="")
stxt = c.create_text(W//2-26, 16, text="Watching", anchor="w", fill=DIM, font=("Segoe UI", 9))
status = tk.StringVar(value="Watching")
def show_status(*_):
    v = status.get()
    c.itemconfig(stxt, text=v)
    c.itemconfig(dot, fill={"Watching": ACCENT, "Reading": "#5aa9ff", "Paused": "#f5b942"}.get(v, DIM))
status.trace_add("write", show_status)

# drag anywhere on the background
drag = {}
def press(e): drag.update(x=e.x, y=e.y)
def move(e): root.geometry(f"+{root.winfo_x() + e.x - drag['x']}+{root.winfo_y() + e.y - drag['y']}")
c.bind("<Button-1>", press); c.bind("<B1-Motion>", move)

# round icon buttons
def icon_button(x, glyph, tip, action, color=FG, y=50, r=15, size=12):
    b = c.create_oval(x-r, y-r, x+r, y+r, fill=PANEL, outline="")
    t = c.create_text(x, y, text=glyph, fill=color, font=("Segoe UI Symbol", size))
    for item in (b, t):
        c.tag_bind(item, "<Enter>", lambda e: (c.itemconfig(b, fill="#3a4256"), c.itemconfig(stxt, text=tip)))
        c.tag_bind(item, "<Leave>", lambda e: (c.itemconfig(b, fill=PANEL), show_status()))
        c.tag_bind(item, "<Button-1>", lambda e: action())
icon_button(32,  "\u23EE", "Back", lambda: flags.update(back=True))
icon_button(72,  "\u25A0", "Stop reading", lambda: flags.update(stop=True))
icon_button(112, "\u275A\u275A", "Pause", lambda: flags.update(pause=True))
icon_button(152, "\u25B6", "Resume", lambda: flags.update(pause=False), ACCENT)
icon_button(192, "\u23ED", "Next", lambda: flags.update(skip=True))
icon_button(W-50, "\u2699", "Speed and pitch", lambda: open_tuner(), y=17, r=11, size=10)
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
    tk.Label(win, text="\u2699  " + speak_state["label"], bg=BG, fg=FG, font=("Segoe UI Semibold", 9)).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 2))
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
    bar2 = tk.Frame(win, bg=BG); bar2.grid(row=3, column=0, columnspan=2, pady=(2, 8))
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
vbox = rounded(224, 37, W-14, 63, 12, fill=PANEL, outline="")
vtxt = c.create_text((224 + W - 14)//2, 50, text="\U0001F3A4 " + short[saved], fill=FG, font=("Segoe UI", 9))
def set_voice(i):
    use_choice(i)
    if tuner["win"] is not None:
        tuner["win"].destroy(); tuner["win"] = None
    open(SAVED, "w").write(short[i])
    c.itemconfig(vtxt, text="\U0001F3A4 " + short[i])
    say("This is " + short[i] + ".")
menu = tk.Menu(root, tearoff=0, bg=PANEL, fg=FG, activebackground="#3a4256", activeforeground=FG, font=("Segoe UI", 9))
for i, n in enumerate(short):
    menu.add_command(label=n, command=lambda i=i: set_voice(i))
menu.add_separator()
menu.add_command(label="\u2795  Get More Voices...", command=lambda: os.startfile("ms-settings:speech"))
def next_voice(e=None):
    menu.tk_popup(e.x_root, e.y_root)
for item in (vbox, vtxt):
    c.tag_bind(item, "<Button-1>", next_voice)
    c.tag_bind(item, "<Enter>", lambda e: c.itemconfig(stxt, text="Change voice"))
    c.tag_bind(item, "<Leave>", lambda e: show_status())

# ---------- watcher loop ----------
_first = bot_replies()
state = {"seen": set(_first), "history": list(_first), "pos": None, "queue": [], "paused": False, "next": 0}
say("Grok Voice is on.")

def tick():
    if flags["quit"]:
        say("Grok Voice is off.", wait=True)
        root.destroy()
        return
    if flags["stop"]:
        flags["stop"] = False
        state["queue"].clear()
        say("")
    if flags["back"]:
        flags["back"] = False
        h = state["history"]
        if h:
            state["pos"] = len(h) - 1 if state["pos"] is None else max(0, state["pos"] - 1)
            state["queue"].clear()
            say(h[state["pos"]])
    if flags["skip"]:   # Next
        flags["skip"] = False
        h = state["history"]
        if state["pos"] is not None and state["pos"] < len(h) - 1:
            state["pos"] += 1          # step forward through history
            state["queue"].clear()
            say(h[state["pos"]])
        else:
            # stop the current reply now and go back to watching for a new one
            state["queue"].clear()
            state["pos"] = None
            say("")
    if flags["pause"] != state["paused"]:
        state["paused"] = flags["pause"]
        state["queue"].clear()
        say("Grok Voice paused." if state["paused"] else "Grok Voice resumed.")
        if not state["paused"]:
            state["seen"] = set(bot_replies())   # skip what came in while paused
    if not state["paused"] and time.time() >= state["next"]:
        state["next"] = time.time() + 2
        try:
            for reply in bot_replies():
                if reply not in state["seen"]:
                    state["seen"].add(reply)
                    state["history"].append(reply)
                    state["pos"] = None
                    state["queue"].append(reply)
        except Exception:
            pass
    speaking = is_speaking()
    if state["queue"] and not speaking:
        say(state["queue"].pop(0))
        speaking = True
    if state["paused"]:
        new = "Paused"
    else:
        new = "Reading" if speaking else "Watching"
    if status.get() != new:
        status.set(new)
    root.after(200, tick)

root.after(200, tick)
root.mainloop()
