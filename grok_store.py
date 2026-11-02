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


def linux_chat_dirs(config_dir, home=None, config_home=None, env=None):
    """Every persistence folder to re-check. A configured path stays the only one."""
    chosen = configured_store(config_dir, env=env)
    if chosen:
        return [chosen] if os.path.isdir(chosen) else []
    home = home or os.path.expanduser("~")
    config_home = config_home or xdg_config_home(home)
    return [path for path in candidate_dirs(home, config_home) if os.path.isdir(path)]


def windows_chat_dirs(appdata, localappdata=None):
    """Persistence folders for every Windows profile root, including a nested account folder."""
    roots = []
    for root in (appdata, localappdata):
        if root and root not in roots:
            roots.append(root)
    found = []

    def add(path):
        path = os.path.normpath(path)
        if path not in found and os.path.isdir(path):
            found.append(path)

    for root in roots:
        for name in APP_DIR_NAMES:
            base = os.path.join(root, name)
            add(os.path.join(base, PERSISTENCE_NAME))
            if not os.path.isdir(base):
                continue
            try:
                children = os.listdir(base)
            except OSError:
                children = []
            for child in children:
                add(os.path.join(base, child, PERSISTENCE_NAME))
    return found


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
    if not isinstance(entry, dict):
        return False
    if entry.get("toAgent"):
        return True
    entry_id = entry.get("id")
    return isinstance(entry_id, str) and entry_id.startswith("agent-outbound")


def _marked_hidden(entry):
    """True when the app stored this object as not drawn in the chat."""
    if not isinstance(entry, dict):
        return False
    if entry.get("hidden") in (True, "true", 1) or entry.get("internal") in (True, "true", 1):
        return True
    if entry.get("visible") in (False, "false", 0) or entry.get("rendered") in (False, "false", 0):
        return True
    visibility = str(entry.get("visibility") or entry.get("display") or "").lower()
    return visibility in ("hidden", "internal", "system", "none")


_FENCE = re.compile(r"```[^\n]*\n(.*?)```|~~~[^\n]*\n(.*?)~~~", re.S)
_MD_LINK = re.compile(r"!\[([^\]]*)\]\([^)]+\)|\[([^\]]+)\]\([^)]+\)|\[([^\]]+)\]\[[^\]]+\]")
_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")


def render_speech(text):
    """The words a person would read on screen, without markdown chrome.

    Links are the label only. Code fences become the words 'code block'.
    Bullets are plain items. Emphasis marks are dropped.
    """
    if not text:
        return ""

    def fence(match):
        body = match.group(1) if match.group(1) is not None else match.group(2)
        if body and body.strip():
            return "\ncode block\n"
        return "\n"

    def link(match):
        return next(group for group in match.groups() if group)

    text = _FENCE.sub(fence, text)
    text = _MD_LINK.sub(link, text)
    text = _AUTOLINK.sub("", text)
    pieces = []
    for raw in text.splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", raw)
        line = re.sub(r"^\s{0,3}>\s?", "", line)
        line = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"__([^_]+)__", r"\1", line)
        line = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", line)
        line = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", line)
        line = re.sub(r"~~([^~]+)~~", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = line.replace("**", "").replace("`", "")
        line = " ".join(line.split())
        if line:
            pieces.append(line)
    return ". ".join(pieces)


def _entry_text(entry):
    """Spoken text of one transcript entry, or '' if the chat does not show it.

    The only allowed shape is a send-message whose message type is text and
    that is not marked hidden. Tool calls, reasoning, status, todos, widgets,
    system turns, and notes to other agents are not that shape.
    """
    if not isinstance(entry, dict) or entry.get("kind") != "send-message":
        return ""
    message = entry.get("message")
    if not isinstance(message, dict) or message.get("type") != "text":
        return ""
    if entry.get("role") == "system" or message.get("role") == "system":
        return ""
    if _is_outbound(entry) or _is_outbound(message):
        return ""
    if _marked_hidden(entry) or _marked_hidden(message):
        return ""
    return render_speech(_text_content(message))


def _message_ids(entry):
    """Every id the app may keep for this bubble, including after a rewrite."""
    found = []
    if not isinstance(entry, dict):
        return found
    message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    for source in (entry, message):
        for field in ("id", "messageId", "clientId", "clientMessageId"):
            value = source.get(field)
            if isinstance(value, str) and value.strip() and value.strip() not in found:
                found.append(value.strip())
    return found


def entry_keys(entry, bot, text):
    """Stable ids for one reply. Position, seq, and timestamp are not included.

    The message id is remembered for the whole session, so a chat switch or a
    rewritten file cannot speak it again. The same on-screen words also match
    when a rewrite assigns a new id but the text is unchanged.
    """
    keys = ["id:" + value for value in _message_ids(entry)]
    rendered = " ".join((text or "").split())
    raw = "%s\n%s" % (bot, rendered)
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
        found.append({
            "account": match.group(1),
            "agent_id": match.group(2),
            "path": path,
            "entries": entries,
            "stamp": stamp,
        })
    return found


# Current selection only. lastSelectedAgentId is the previous bot, and treating
# it as a second vote made a bot switch look ambiguous and fall back to the
# old conversation.
_CURRENT_AGENT_KEYS = {
    "selectedagentid", "activeagentid", "currentagentid", "openagentid",
    "focusedagentid", "selectedagent", "activeagent", "currentagent",
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


def _document_value(path):
    try:
        parsed = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(parsed, dict) and "value" in parsed:
        return parsed.get("value")
    return parsed


def _current_agent_ids(value, known, found):
    """Agent ids named as the open bot. Previous-bot fields are ignored."""
    if isinstance(value, dict):
        for key, item in value.items():
            if _key_name(key) in _CURRENT_AGENT_KEYS and isinstance(item, str) and item in known:
                found.add(item)
            else:
                _current_agent_ids(item, known, found)
    elif isinstance(value, list):
        for item in value:
            _current_agent_ids(item, known, found)


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def _known_accounts(slices, rows):
    accounts = {row["account"] for row in rows}
    for key, _path in slices:
        match = ROSTER_SLICE.match(key)
        if match:
            accounts.add(match.group(1))
    return accounts


def _account_for_key(key, accounts):
    """Account id embedded in a slice key, or None for a global slice."""
    prefix = "sand.client.slice.account."
    if not key.startswith(prefix):
        return None
    rest = key[len(prefix):]
    matches = [account for account in accounts if rest.startswith(account + ".")]
    if not matches:
        return None
    matches.sort(key=len, reverse=True)
    return matches[0]


def _selection_hits(slices, accounts, known):
    """(mtime, agent id, account or None) for slices that name one open bot.

    The newest hit wins. An older account's saved selection cannot outvote
    the account that was just opened.
    """
    hits = []
    for key, path in slices:
        if "transcript.replicas" in key or not _is_selection_slice(key):
            continue
        value = _document_value(path)
        if value is None:
            continue
        found = set()
        _current_agent_ids(value, known, found)
        if len(found) != 1:
            continue
        hits.append((_mtime(path), next(iter(found)), _account_for_key(key, accounts)))
    return hits


def _freshest_account(slices, accounts):
    """Account whose UI state was written last. Transcript writes do not count.

    A background bot keeps updating its own transcript. That must not pull
    the reader off the account Chip just switched to.
    """
    best = None
    best_mtime = None
    for key, path in slices:
        if "transcript.replicas" in key:
            continue
        account = _account_for_key(key, accounts)
        if account not in accounts:
            continue
        stamp = _mtime(path)
        if best_mtime is None or stamp > best_mtime:
            best = account
            best_mtime = stamp
    return best


def _roster_selected_id(slices, account, known):
    chosen = []
    for key, path in slices:
        match = ROSTER_SLICE.match(key)
        if not match or match.group(1) != account:
            continue
        value = _load_value(path) or {}
        for row in value.get("rows") or []:
            if not isinstance(row, dict):
                continue
            agent_id = row.get("id")
            if not isinstance(agent_id, str) or agent_id not in known:
                continue
            if any(_flag_is_on(row, flag) for flag in _SELECTED_FLAGS):
                chosen.append(agent_id)
    if len(chosen) == 1:
        return chosen[0]
    return None


def is_grok_window_title(text):
    """True for a Grok Bot window, including 'Larry — Grok Bot'. Not our toolbar."""
    folded = " ".join(str(text or "").split()).lower()
    if not folded or "grokbot voice" in folded:
        return False
    return "grok bot" in folded


def grok_titles_from_names(names):
    """Window names that belong to Grok Bot, in the order they were seen."""
    titles = []
    for name in names or []:
        text = " ".join(str(name or "").split())
        if is_grok_window_title(text) and text not in titles:
            titles.append(text)
    return titles


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


def _store_list(directory, directories):
    folders = []
    for folder in list(directories or []) + ([directory] if directory else []):
        if folder and folder not in folders:
            folders.append(folder)
    return folders


def _load_stores(folders):
    slices = []
    rows = []
    names = {}
    for folder in folders:
        for key, path in _slices(folder):
            slices.append((key, path))
        rows.extend(_transcripts(folder))
        names.update(roster_names(folder))
    return slices, rows, names


def _row_for(rows, account, agent_id):
    matches = [row for row in rows if row["agent_id"] == agent_id and (account is None or row["account"] == account)]
    if account is None and len(matches) == 1:
        return matches[0]
    for row in matches:
        if row["account"] == account:
            return row
    return None


def _chat_was_opened(row):
    """True when the transcript file was saved again without a new message.

    Opening a chat rewrites its file. A bot reply does not: the newest
    message and the file time match. The window title is not used.
    """
    newest = None
    for entry in row["entries"]:
        if isinstance(entry, dict) and isinstance(entry.get("timestampMs"), (int, float)):
            stamp = entry["timestampMs"]
            newest = stamp if newest is None else max(newest, stamp)
    if newest is None:
        return False
    return row["stamp"] > (newest / 1000.0) + 5


def _focused_opens(rows):
    """The chat whose file was saved again well after the others, or none.

    A sync that rewrites every transcript at once is not a bot switch.
    """
    opened = [row for row in rows if _chat_was_opened(row)]
    if len(opened) <= 1:
        return opened
    opened.sort(key=lambda row: row["stamp"])
    if opened[-1]["stamp"] > opened[-2]["stamp"] + 5:
        return [opened[-1]]
    return []


def active_transcript(directory, window_titles=None, directories=None):
    """The conversation on screen now, from the saved files only.

    The window title is ignored on every platform. A bare "Grok Bot" title
    names no bot, and a title that does is still not the source of truth.
    The open chat is the transcript that was rewritten when it was shown,
    if exactly one was. Otherwise it is the saved selection, then a roster
    row marked selected, then the only transcript in the account. Several
    chats and no fresh signal means we are not sure: return None so Back
    stays quiet instead of playing a different bot.
    """
    del window_titles  # titles are not a signal; callers may still pass them
    slices, rows, _names = _load_stores(_store_list(directory, directories))
    if not rows:
        return None
    accounts = _known_accounts(slices, rows)
    known = {row["agent_id"] for row in rows}
    account = _freshest_account(slices, accounts)
    if account is None:
        present = {row["account"] for row in rows}
        account = next(iter(present)) if len(present) == 1 else None
    if account is None:
        return None
    scoped = [row for row in rows if row["account"] == account]
    hits = [hit for hit in _selection_hits(slices, accounts, known) if hit[2] in (None, account)]
    hits.sort()
    selection_mtime = hits[-1][0] if hits else None
    selection_id = hits[-1][1] if hits else None
    opened = _focused_opens(scoped)
    if len(opened) == 1 and (selection_mtime is None or opened[0]["stamp"] > selection_mtime + 0.5):
        return opened[0]
    if selection_id:
        chosen = _row_for(scoped, account, selection_id)
        if chosen is not None:
            return chosen
    selected = _roster_selected_id(slices, account, known)
    chosen = _row_for(scoped, account, selected) if selected else None
    if chosen is not None:
        return chosen
    if len(scoped) == 1:
        return scoped[0]
    return None


def latest_replay(lines):
    """The reply Back plays for the chat that is open. None when that chat is unknown."""
    if not lines:
        return None
    return lines[-1]


def reply_snapshot(directory, window_titles=None, directories=None):
    """(lines, bot names, key lists, active file) for the open chat.

    key lists identify replies without using their position. active file is
    the transcript path, or None when there is no chat to follow.
    window_titles are ignored. Every call re-reads the stores. None for the
    active file means the open chat is not known, so nothing should be spoken.
    """
    folders = _store_list(directory, directories)
    names = {}
    for folder in folders:
        names.update(roster_names(folder))
    transcript = active_transcript(directory, window_titles=window_titles, directories=directories)
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
