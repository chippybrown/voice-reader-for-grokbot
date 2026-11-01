# Read Grok Bot's on-disk chat mirror.
import hashlib
#
# The desktop app (Electron, bundle id com.anysphere.sand) keeps a sliding
# window of each bot's transcript in sand-client-persistence/*.blob. Each
# filename is the lowercase, unpadded base32 of a slice key, and the file is
# JSON: {"schemaVersion": N, "value": ...}. Transcript slices hold
# value.entries. The roster slice holds value.rows of bots.
import base64
import glob
import json
import os
import re
import time


PERSISTENCE_NAME = "sand-client-persistence"
APP_DIR_NAMES = ("Grok Bot", "grok-bot", "Grokbot")
TRANSCRIPT_SLICE = re.compile(r"^sand\.client\.slice\.account\.(.+)\.transcript\.replicas\.(.+)$")
ROSTER_SLICE = re.compile(r"^sand\.client\.slice\.account\.(.+)\.roster\.last-roster$")
_BASE32 = "abcdefghijklmnopqrstuvwxyz234567"


def decode_base32(name):
    """RFC 4648 base32, lowercase and without padding. None if it is not a slice name."""
    value = 0
    bits = 0
    out = bytearray()
    for char in name.strip().lower():
        index = _BASE32.find(char)
        if index < 0:
            return None
        value = (value << 5) | index
        bits += 5
        if bits >= 8:
            bits -= 8
            out.append((value >> bits) & 0xFF)
    if not out:
        return None
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return None


def encode_base32(text):
    """Lowercase unpadded base32, matching the app's blob filenames."""
    raw = base64.b32encode(text.encode("utf-8")).decode("ascii").lower()
    return raw.rstrip("=")


def xdg_config_home(home=None):
    home = home or os.path.expanduser("~")
    env = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if env and home is None:
        return env
    if home == os.path.expanduser("~") and env:
        return env
    return os.path.join(home, ".config")


def normalize_store(path):
    """Accept either the persistence folder or the Grok Bot config folder above it."""
    path = os.path.expanduser(path.strip())
    nested = os.path.join(path, PERSISTENCE_NAME)
    if os.path.isdir(nested):
        return nested
    return path


def candidate_dirs(home, config_home=None):
    """Common places the Linux app stores sand-client-persistence, most likely first."""
    home = os.path.expanduser(home)
    config_home = config_home or os.path.join(home, ".config")
    found = []

    def add(path):
        path = os.path.normpath(path)
        if path not in found:
            found.append(path)

    for root in (config_home, os.path.join(home, ".config")):
        for name in APP_DIR_NAMES:
            add(os.path.join(root, name, PERSISTENCE_NAME))

    var_app = os.path.join(home, ".var", "app")
    if os.path.isdir(var_app):
        try:
            apps = os.listdir(var_app)
        except OSError:
            apps = []
        for app in apps:
            config = os.path.join(var_app, app, "config")
            for name in APP_DIR_NAMES:
                add(os.path.join(config, name, PERSISTENCE_NAME))
            add(os.path.join(config, PERSISTENCE_NAME))

    snap = os.path.join(home, "snap")
    if os.path.isdir(snap):
        try:
            snaps = os.listdir(snap)
        except OSError:
            snaps = []
        for name in snaps:
            for rev in ("current", "common"):
                base = os.path.join(snap, name, rev, ".config")
                for app_name in APP_DIR_NAMES:
                    add(os.path.join(base, app_name, PERSISTENCE_NAME))

    return found


def _blob_mtime(path):
    blobs = glob.glob(os.path.join(path, "*.blob"))
    if not blobs:
        return None
    try:
        return max(os.path.getmtime(blob) for blob in blobs)
    except OSError:
        return None


def choose_store(candidates):
    """Pick the folder that actually has chat files. Earlier candidates win ties."""
    existing = [path for path in candidates if os.path.isdir(path)]
    if not existing:
        return None
    scored = []
    for index, path in enumerate(existing):
        stamp = _blob_mtime(path)
        scored.append((1 if stamp is not None else 0, stamp or 0, -index, path))
    scored.sort(reverse=True)
    return scored[0][3]


def configured_store(config_dir, env=None):
    """GROKBOT_CHAT_DIR, then chat-folder.txt in the Grokbot Voice config dir."""
    env = os.environ if env is None else env
    raw = (env.get("GROKBOT_CHAT_DIR") or "").strip()
    if not raw:
        pointer = os.path.join(config_dir, "chat-folder.txt")
        try:
            raw = open(pointer, encoding="utf-8").read().strip()
        except OSError:
            raw = ""
    if not raw:
        return None
    return normalize_store(raw)


def linux_store(config_dir, home=None, config_home=None, env=None):
    """Configured folder if set, otherwise the newest auto-detected one."""
    chosen = configured_store(config_dir, env=env)
    if chosen:
        return chosen
    return choose_store(candidate_dirs(home or os.path.expanduser("~"), config_home))


def _read_text(path):
    prefix = "\\\\?\\" if os.name == "nt" else ""
    with open(prefix + os.path.abspath(path), encoding="utf-8", errors="ignore") as handle:
        return handle.read()


def _load_value(path):
    try:
        parsed = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("value")
    return value if isinstance(value, dict) else None


def _slices(directory):
    if not directory or not os.path.isdir(directory):
        return []
    rows = []
    for name in os.listdir(directory):
        if not name.endswith(".blob"):
            continue
        key = decode_base32(name[:-5])
        if not key:
            continue
        path = os.path.join(directory, name)
        rows.append((key, path))
    return rows


def roster_rows(directory):
    """Roster entries in file order."""
    rows = []
    for key, path in _slices(directory):
        if not ROSTER_SLICE.match(key):
            continue
        value = _load_value(path) or {}
        for row in value.get("rows") or []:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def roster_names(directory):
    """agent id -> sidebar name."""
    names = {}
    for row in roster_rows(directory):
        agent_id = row.get("id")
        name = row.get("name")
        if isinstance(agent_id, str) and isinstance(name, str) and name.strip():
            names[agent_id] = name.strip()
    return names


def chief_voice(directory, name):
    """The bot's saved voiceId from whatever slice stores it. ('carina', 1.0) for Moya."""
    pat = re.compile(r'\{"id":"[0-9a-f-]{36}","name":"%s"' % re.escape(name))
    vpat = re.compile(r'"voiceId":"([a-z]+)","voiceSpeed":([\d.]+)')
    if directory and os.path.isdir(directory):
        for blob in glob.glob(os.path.join(directory, "*.blob")):
            try:
                text = _read_text(blob)
            except OSError:
                continue
            for match in pat.finditer(text):
                voice = vpat.search(text, match.end(), match.end() + 8000)
                if voice:
                    return voice.group(1), float(voice.group(2))
    if name == "Moya":
        return ("carina", 1.0)
    return (None, 1.0)


def piper_voice_choices(piper_dir):
    """(label, 'piper', onnx path) for each model file in the folder."""
    files = sorted(glob.glob(os.path.join(piper_dir, "*.onnx")))
    keys = [os.path.basename(path).split("-")[1] if "-" in os.path.basename(path) else os.path.basename(path) for path in files]
    choices = []
    for path in files:
        base = os.path.basename(path)
        parts = base.split("-")
        key = parts[1] if len(parts) > 1 else base[:-5]
        quality = base[:-5].split("-")[-1]
        nice = {"jenny_dioco": "Jenny", "ljspeech": "LJ Speech"}.get(key, key.replace("_", " ").title())
        if keys.count(key) > 1 and quality != "medium":
            nice += " " + quality.title()
        choices.append((nice + " (natural)", "piper", path))
    return choices


def _text_content(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(part for part in (_text_content(item) for item in value) if part).strip()
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"].strip()
        if "content" in value:
            return _text_content(value.get("content"))
    return ""


def _is_outbound(entry):
    """Messages the bot sent to another agent, not to the person."""
    if entry.get("toAgent"):
        return True
    entry_id = entry.get("id")
    return isinstance(entry_id, str) and entry_id.startswith("agent-outbound")


def _entry_text(entry):
    """Spoken text of one transcript entry, or '' if it is not a reply to the user.

    User-facing replies are send-message entries whose message type is text,
    and assistant messages that are not addressed to another agent.
    """
    if _is_outbound(entry):
        return ""
    kind = entry.get("kind")
    if kind == "send-message":
        message = entry.get("message")
        if not isinstance(message, dict) or message.get("type") != "text":
            return ""
        return _text_content(message)
    if kind == "message" and entry.get("role") == "assistant":
        return _text_content(entry.get("content"))
    return ""


def entry_keys(entry, bot, text):
    """Stable ids for one reply. Position and seq are not included.

    A rewritten or compacted slice keeps the same message id, or the same
    bot, kind, timestamp, and text. Either one is enough to recognize it.
    """
    keys = []
    entry_id = entry.get("id")
    if isinstance(entry_id, str) and entry_id.strip():
        keys.append("id:" + entry_id.strip())
    stamp = entry.get("timestampMs")
    raw = "%s\n%s\n%s\n%s" % (bot, entry.get("kind") or "", "" if stamp is None else stamp, text)
    keys.append("h:" + hashlib.sha256(raw.encode("utf-8")).hexdigest())
    return keys


def _clock(timestamp_ms):
    try:
        stamp = time.localtime(float(timestamp_ms) / 1000.0)
    except (TypeError, ValueError, OverflowError, OSError):
        return ""
    clock = time.strftime("%I:%M:%S %p", stamp)
    return clock[1:] if clock.startswith("0") else clock


def _transcripts(directory):
    found = []
    for key, path in _slices(directory):
        match = TRANSCRIPT_SLICE.match(key)
        if not match:
            continue
        value = _load_value(path) or {}
        entries = value.get("entries")
        if not isinstance(entries, list):
            continue
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            stamp = 0
        persisted = value.get("persistedAt")
        if isinstance(persisted, (int, float)) and persisted > 1000000000000:
            stamp = max(stamp, persisted / 1000.0)
        found.append({"agent_id": match.group(2), "path": path, "entries": entries, "stamp": stamp})
    return found


_EXPLICIT_AGENT_KEYS = {
    "selectedagentid", "activeagentid", "currentagentid", "openagentid",
    "focusedagentid", "lastselectedagentid", "selectedagent", "activeagent",
    "currentagent",
}
_SELECTED_FLAGS = ("selected", "active", "isSelected", "isActive", "isCurrent", "isOpen")
_SELECTION_HINTS = (
    "selected-agent", "selectedagent", "active-agent", "activeagent",
    "current-agent", "currentagent", "ui-layout", "ui.layout", "ui.selection",
    "focused-agent", "open-conversation", "last-opened", "lastopened",
)


def _key_name(key):
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _is_selection_slice(key):
    if "transcript.replicas" in key:
        return False
    lowered = key.lower()
    return any(hint in lowered for hint in _SELECTION_HINTS)


def _flag_is_on(row, flag):
    return row.get(flag) in (True, "true", 1)


def _selected_roster_id(directory, known):
    chosen = []
    for row in roster_rows(directory):
        agent_id = row.get("id")
        if not isinstance(agent_id, str) or agent_id not in known:
            continue
        if any(_flag_is_on(row, flag) for flag in _SELECTED_FLAGS):
            chosen.append(agent_id)
    if len(chosen) == 1:
        return chosen[0]
    return None


def _document_value(path):
    try:
        parsed = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(parsed, dict) and "value" in parsed:
        return parsed.get("value")
    return parsed


def _collect_agent_ids(value, known, explicit, loose, loose_ok):
    if isinstance(value, dict):
        agent = value.get("id") if isinstance(value.get("id"), str) else value.get("agentId")
        if loose_ok and isinstance(agent, str) and agent in known and any(_flag_is_on(value, flag) for flag in _SELECTED_FLAGS):
            explicit.add(agent)
        for key, item in value.items():
            if _key_name(key) in _EXPLICIT_AGENT_KEYS and isinstance(item, str) and item in known:
                explicit.add(item)
            elif loose_ok and _key_name(key) in ("agentid", "conversationid") and isinstance(item, str) and item in known:
                loose.add(item)
            else:
                _collect_agent_ids(item, known, explicit, loose, loose_ok)
    elif isinstance(value, list):
        for item in value:
            _collect_agent_ids(item, known, explicit, loose, loose_ok)
    elif loose_ok and isinstance(value, str) and value in known:
        loose.add(value)


def _selected_slice_id(directory, known):
    """An agent id named by a selection slice, or None when that is ambiguous."""
    explicit = set()
    loose = set()
    for key, path in _slices(directory):
        if "transcript.replicas" in key:
            continue
        value = _document_value(path)
        if value is None:
            continue
        _collect_agent_ids(value, known, explicit, loose, _is_selection_slice(key))
    if len(explicit) == 1:
        return next(iter(explicit))
    if not explicit and len(loose) == 1:
        return next(iter(loose))
    return None


def agent_id_from_titles(titles, names):
    """Roster agent id named by a window title. None when the title is ambiguous.

    names is agent id -> sidebar name. The longest matching name wins, so
    'Vision Design' beats 'Vision'. The bare app title is not a bot.
    """
    winners = {}
    for title in titles or []:
        text = " ".join(str(title or "").split())
        if not text or text.lower() in ("grok bot", "grokbot", "grok", "grokbot voice"):
            continue
        folded = text.lower()
        hits = []
        for agent_id, name in names.items():
            label = " ".join(str(name or "").split())
            if label and label.lower() in folded:
                hits.append((len(label), agent_id))
        if not hits:
            continue
        hits.sort(reverse=True)
        best = hits[0][0]
        top = [agent_id for length, agent_id in hits if length == best]
        if len(top) == 1:
            winners[top[0]] = True
    if len(winners) == 1:
        return next(iter(winners))
    return None


def _user_message_stamp(entry):
    """timestampMs of a message the person sent, not a bot or an agent note."""
    if not isinstance(entry, dict) or _is_outbound(entry):
        return None
    if entry.get("kind") != "message" or entry.get("role") != "user":
        return None
    stamp = entry.get("timestampMs")
    if isinstance(stamp, (int, float)):
        return stamp
    return None


def _latest_user_transcript(rows):
    best = None
    best_stamp = None
    for row in rows:
        stamps = [_user_message_stamp(entry) for entry in row["entries"]]
        stamps = [stamp for stamp in stamps if stamp is not None]
        if not stamps:
            continue
        stamp = max(stamps)
        if best_stamp is None or stamp > best_stamp:
            best = row
            best_stamp = stamp
    return best


def active_transcript(directory, window_titles=None):
    """The conversation open in Grok Bot, not whichever bot wrote most recently.

    A background bot updates its own transcript while Chip is looking at
    another chat. The open chat is, in order: a selected agent saved in the
    persistence slices, a roster row marked selected, the bot named in the
    window title, then the conversation with the newest message from the
    user. The newest file is only the last resort when none of those exist.
    """
    rows = _transcripts(directory)
    if not rows:
        return None
    by_id = {row["agent_id"]: row for row in rows}
    known = set(by_id)
    selected = _selected_slice_id(directory, known) or _selected_roster_id(directory, known)
    if selected in by_id:
        return by_id[selected]
    named = agent_id_from_titles(window_titles, roster_names(directory))
    if named in by_id:
        return by_id[named]
    latest = _latest_user_transcript(rows)
    if latest is not None:
        return latest
    rows.sort(key=lambda row: row["stamp"])
    return rows[-1]


def reply_snapshot(directory, window_titles=None):
    """(lines, bot names, key lists, active file) for the open chat.

    key lists identify replies without using their position. active file is
    the transcript path, or None when there is no chat to follow.
    window_titles are Grok Bot window titles, used when no saved selection
    names the open agent.
    """
    names = roster_names(directory)
    transcript = active_transcript(directory, window_titles=window_titles)
    if transcript is None:
        return [], sorted(names.values(), key=len, reverse=True), [], None
    agent_id = transcript["agent_id"]
    bot = names.get(agent_id) or "Bot"
    lines = []
    keylists = []
    entries = list(transcript["entries"])
    entries.sort(key=lambda entry: entry.get("seq") if isinstance(entry, dict) and isinstance(entry.get("seq"), int) else 0)
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        text = _entry_text(entry)
        if not text:
            continue
        seq = entry.get("seq")
        if not isinstance(seq, int):
            seq = index + 1
        clock = _clock(entry.get("timestampMs")) or "12:00:00 PM"
        lines.append("%s %s #%s %s" % (bot, clock, seq, text))
        keylists.append(entry_keys(entry, bot, text))
    bot_names = sorted(set(list(names.values()) + [bot]), key=len, reverse=True)
    return lines, bot_names, keylists, transcript["path"]


def reply_lines(directory):
    """(lines, bot names) for the active chat."""
    lines, names, _keys, _active = reply_snapshot(directory)
    return lines, names


def mark_seen(seen, keylists):
    """Record every current reply. Nothing already in the file is read."""
    for keys in keylists:
        seen.update(keys)


def launch_is_baseline(seen, lines, previous):
    """True for the first on-screen view after a start that saw nothing yet.

    A window that is not ready at launch must not be treated as a new chat.
    The replies already there are history. Back and Next can reach them.
    """
    if not lines or previous:
        return False
    return not any(line in seen for line in lines)


def unseen_lines(seen, lines, keylists):
    """Lines whose message id or content hash has not been seen yet.

    Matching keys are recorded. A later rewrite that only changes seq or
    order does not come back as a new reply.
    """
    fresh = []
    for line, keys in zip(lines, keylists):
        if any(key in seen for key in keys):
            seen.update(keys)
            continue
        seen.update(keys)
        fresh.append(line)
    return fresh
