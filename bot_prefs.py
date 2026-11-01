# Per-bot voice and which bots are read aloud. No UI here, so tests can
# load the rules without opening a window.

TOOLBAR_TIPS = {
    "back": "Back: read the previous reply",
    "stop": "Stop (Ctrl+Alt+S): stop reading and stop monitoring",
    "pause": "Pause (Ctrl+Alt+P): hold in the middle of this reply",
    "play": "Play: start monitoring, or continue a paused reply",
    "next": "Next: step forward through earlier replies",
    "gear": "Gear: Settings",
    "power": "Turn off (Ctrl+Alt+Q)",
}


def fresh():
    """New install: bots that show up later are read aloud."""
    return {"new_bots": True, "bots": {}}


def normalize(data):
    """A stored document, with missing pieces filled in."""
    if not isinstance(data, dict):
        data = {}
    bots = data.get("bots")
    if not isinstance(bots, dict):
        bots = {}
    clean = {}
    for name, row in bots.items():
        label = " ".join(str(name or "").split())
        if not label:
            continue
        clean[label] = dict(row) if isinstance(row, dict) else {}
    return {"new_bots": bool(data.get("new_bots", True)), "bots": clean}


def note_bots(prefs, names):
    """Remember bots that have appeared. Does not decide read-aloud for them."""
    for name in names or []:
        label = " ".join(str(name or "").split())
        if label and label not in prefs["bots"]:
            prefs["bots"][label] = {}
    return prefs


def allows_auto(prefs, bot):
    """False when this bot is unchecked. A bot with no choice follows new_bots."""
    label = " ".join(str(bot or "").split())
    if not label:
        return True
    row = prefs["bots"].get(label)
    if not isinstance(row, dict) or "read" not in row:
        return bool(prefs.get("new_bots", True))
    return bool(row.get("read"))


def voice_choice(prefs, bot):
    """(voice label or '', speed or None, pitch or None).

    An empty voice label means the default voice. Missing speed or pitch
    means that voice's own saved speed and pitch.
    """
    label = " ".join(str(bot or "").split())
    row = prefs["bots"].get(label) if label else None
    if not isinstance(row, dict):
        return "", None, None
    voice = " ".join(str(row.get("voice") or "").split())
    speed = row.get("speed")
    pitch = row.get("pitch")
    if not isinstance(speed, (int, float)):
        speed = None
    if not isinstance(pitch, (int, float)):
        pitch = None
    return voice, speed, pitch
