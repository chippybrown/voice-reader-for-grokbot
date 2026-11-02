# Read Grok Bot's on-disk chat mirror.
import hashlib
#
# The desktop app (Electron, bundle id com.anysphere.sand) keeps a sliding
# window of each bot's transcript in sand-client-persistence/*.blob. Each
# filename is the lowercase, unpadded base32 of a slice key, and the file is
# JSON: {"schemaVersion": N, "value": ...}. Transcript slices hold
# value.entries. The roster slice holds value.rows of bots.
import base64
import json
import os
import re
import time
import unicodedata


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


def extended_path(path):
    """Path for open, stat, and listdir. On Windows, \\\\?\\ or \\\\?\\UNC\\.

    LongPathsEnabled stays untouched. The prefix is what lets a path over
    260 characters open, with no admin change and no longPathAware manifest.
    Other systems get the same path they passed in.
    """
    if path is None or path == "":
        return path
    if os.name != "nt":
        return path
    text = os.fspath(path).replace("/", "\\")
    if text.startswith("\\\\?\\"):
        return text
    return _windows_long_path(os.path.abspath(text))


def _windows_long_path(absolute):
    text = absolute.replace("/", "\\")
    if text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def normalize_store(path):
    """Accept either the persistence folder or the Grok Bot config folder above it."""
    path = os.path.expanduser(path.strip())
    nested = os.path.join(path, PERSISTENCE_NAME)
    if os.path.isdir(extended_path(nested)):
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
    if os.path.isdir(extended_path(var_app)):
        try:
            apps = os.listdir(extended_path(var_app))
        except OSError:
            apps = []
        for app in apps:
            config = os.path.join(var_app, app, "config")
            for name in APP_DIR_NAMES:
                add(os.path.join(config, name, PERSISTENCE_NAME))
            add(os.path.join(config, PERSISTENCE_NAME))

    snap = os.path.join(home, "snap")
    if os.path.isdir(extended_path(snap)):
        try:
            snaps = os.listdir(extended_path(snap))
        except OSError:
            snaps = []
        for name in snaps:
            for rev in ("current", "common"):
                base = os.path.join(snap, name, rev, ".config")
                for app_name in APP_DIR_NAMES:
                    add(os.path.join(base, app_name, PERSISTENCE_NAME))

    return found


def _blob_mtime(path):
    try:
        names = os.listdir(extended_path(path))
    except OSError:
        return None
    stamps = []
    for name in names:
        if not name.endswith(".blob"):
            continue
        try:
            stamps.append(os.path.getmtime(extended_path(os.path.join(path, name))))
        except OSError:
            continue
    if not stamps:
        return None
    return max(stamps)


def choose_store(candidates):
    """Pick the folder that actually has chat files. Earlier candidates win ties."""
    existing = [path for path in candidates if os.path.isdir(extended_path(path))]
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
            raw = open(extended_path(pointer), encoding="utf-8").read().strip()
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
        return [chosen] if os.path.isdir(extended_path(chosen)) else []
    home = home or os.path.expanduser("~")
    config_home = config_home or xdg_config_home(home)
    return [path for path in candidate_dirs(home, config_home) if os.path.isdir(extended_path(path))]


def windows_chat_dirs(appdata, localappdata=None):
    """Persistence folders for every Windows profile root, including a nested account folder."""
    roots = []
    for root in (appdata, localappdata):
        if root and root not in roots:
            roots.append(root)
    found = []

    def add(path):
        path = os.path.normpath(path)
        if path not in found and os.path.isdir(extended_path(path)):
            found.append(path)

    for root in roots:
        for name in APP_DIR_NAMES:
            base = os.path.join(root, name)
            add(os.path.join(base, PERSISTENCE_NAME))
            if not os.path.isdir(extended_path(base)):
                continue
            try:
                children = os.listdir(extended_path(base))
            except OSError:
                children = []
            for child in children:
                add(os.path.join(base, child, PERSISTENCE_NAME))
    return found


def _read_text(path):
    with open(extended_path(path), encoding="utf-8", errors="ignore") as handle:
        return handle.read()


# path -> (mtime_ns, ctime_ns, size, mtime, parsed json).
# Idle polling must not re-read unchanged chats. A failed read is not stored:
# Grok Bot often still has the file open while it is being replaced, and
# remembering that failure hid every later reply until the timestamp changed.
_json_cache = {}
_read_problems = {}


def _stat_token(stat):
    mtime_ns = getattr(stat, "st_mtime_ns", None) or 0
    if not mtime_ns:
        mtime_ns = int(float(stat.st_mtime) * 1000000000)
    ctime_ns = getattr(stat, "st_ctime_ns", 0) or 0
    return (mtime_ns, ctime_ns, stat.st_size, stat.st_mtime)


def note_read_problem(path, message):
    """Remember one read failure. Returns the log line the first time, else None."""
    text = "%s: %s" % (os.path.basename(path), message)
    if _read_problems.get(path) == text:
        return None
    _read_problems[path] = text
    return "skip new reply: could not read the chat file | " + text


def clear_read_problem(path):
    _read_problems.pop(path, None)


def _parsed_json(path):
    """Parse a blob once until its size or modification time changes.

    A file that disappears between the directory listing and the read is
    skipped. The failure is not stored, and it is tried once more in case
    the replacement file is already in place.
    """
    for attempt in (1, 2):
        try:
            stat = os.stat(extended_path(path))
        except OSError as exc:
            if attempt == 1 and isinstance(exc, (FileNotFoundError, PermissionError)):
                continue
            note_read_problem(path, exc.__class__.__name__)
            return None
        token = _stat_token(stat)
        cached = _json_cache.get(path)
        if cached and cached[0] == token:
            clear_read_problem(path)
            return cached[1]
        try:
            parsed = json.loads(_read_text(path))
        except (FileNotFoundError, PermissionError) as exc:
            if attempt == 1:
                continue
            note_read_problem(path, exc.__class__.__name__)
            _json_cache.pop(path, None)
            return None
        except (OSError, json.JSONDecodeError) as exc:
            if attempt == 1 and isinstance(exc, json.JSONDecodeError):
                continue
            note_read_problem(path, exc.__class__.__name__)
            _json_cache.pop(path, None)
            return None
        _json_cache[path] = (token, parsed)
        clear_read_problem(path)
        return parsed
    note_read_problem(path, "FileNotFoundError")
    return None


def _load_value(path):
    parsed = _parsed_json(path)
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("value")
    return value if isinstance(value, dict) else None


def _slices(directory):
    """Blob names that were present when the folder was listed.

    A name can vanish before it is read. Grok Bot writes a temp file and
    renames it onto the blob. That one missing file is skipped later; it
    must not abandon the rest of the folder.
    """
    if not directory or not os.path.isdir(extended_path(directory)):
        return []
    try:
        names = os.listdir(extended_path(directory))
    except OSError as exc:
        note_read_problem(directory, exc.__class__.__name__)
        return []
    rows = []
    for name in names:
        if not name.endswith(".blob"):
            continue
        key = decode_base32(name[:-5])
        if not key:
            continue
        rows.append((key, os.path.join(directory, name)))
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
    if directory and os.path.isdir(extended_path(directory)):
        try:
            names = os.listdir(extended_path(directory))
        except OSError:
            names = []
        for blob_name in names:
            if not blob_name.endswith(".blob"):
                continue
            blob = os.path.join(directory, blob_name)
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
    try:
        names = os.listdir(extended_path(piper_dir))
    except OSError:
        names = []
    files = sorted(os.path.join(piper_dir, name) for name in names if name.endswith(".onnx"))
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


def plain_label(text):
    """Letters and numbers only, so an emoji in a bot name is not spoken or logged as '?'."""
    kept = []
    for char in str(text or ""):
        if char == "\ufffd":
            continue
        category = unicodedata.category(char)
        if category.startswith(("L", "N", "Z")) or (category.startswith("P") and char.isascii() and char != "?"):
            kept.append(char)
        elif char in "&/-+*'":
            kept.append(char)
    cleaned = "".join(kept)
    cleaned = re.sub(r"(?<=\S)\?(?=\s)", "", cleaned)
    return " ".join(cleaned.split())


def speech_key(text):
    """Identity of words already spoken. Emoji and symbols do not make a new line."""
    plain = plain_label(text)
    if not plain:
        return ""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def allow_auto_speech(spoken, text, replay=False):
    """False when this automatic read was already spoken. Back may repeat it."""
    key = speech_key(text)
    if not key:
        return bool(replay)
    if key in spoken and not replay:
        return False
    spoken.add(key)
    return True


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
    return plain_label(". ".join(pieces))


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
    rendered = plain_label(text)
    raw = "%s\n%s" % (plain_label(bot), rendered)
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
        try:
            match = TRANSCRIPT_SLICE.match(key)
            if not match:
                continue
            value = _load_value(path) or {}
            entries = value.get("entries")
            if not isinstance(entries, list):
                continue
            try:
                stamp = os.path.getmtime(extended_path(path))
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
        except Exception as exc:
            note_read_problem(path, exc.__class__.__name__)
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
    parsed = _parsed_json(path)
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
        return os.path.getmtime(extended_path(path))
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


def _selection_strength(key):
    """selected-agent is this window. last-opened is often another device."""
    lowered = key.lower()
    weak = ("last-opened", "lastopened", "open-conversation")
    strong = (
        "selected-agent", "selectedagent", "active-agent", "activeagent",
        "current-agent", "currentagent", "focused-agent", "ui.selection", "ui-selection",
    )
    if any(hint in lowered for hint in weak) and not any(hint in lowered for hint in strong):
        return "weak"
    if _is_selection_slice(key):
        return "strong"
    return None


def _selection_hits(slices, accounts, known):
    """(mtime, agent id, account or None, strength) for slices that name one open bot.

    The newest strong hit wins. last-opened is kept only when nothing stronger
    exists, because another device rewrites that slice while this window stays put.
    """
    hits = []
    for key, path in slices:
        if "transcript.replicas" in key or not _is_selection_slice(key):
            continue
        strength = _selection_strength(key)
        if not strength:
            continue
        value = _document_value(path)
        if value is None:
            continue
        found = set()
        _current_agent_ids(value, known, found)
        if len(found) != 1:
            continue
        hits.append((_mtime(path), next(iter(found)), _account_for_key(key, accounts), strength))
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


_scan = {"files": 0, "newest": None}


def last_scan():
    """(blob count, newest mtime or None) from the last folder read."""
    return _scan["files"], _scan["newest"]


def watch_heartbeat(files, newest):
    """One status line. A minute with no new line means the poll has stalled."""
    if newest:
        stamp = time.strftime("%H:%M:%S", time.localtime(newest))
    else:
        stamp = "none"
    return "watching: %d files, last change %s" % (int(files or 0), stamp)


def _load_stores(folders):
    slices = []
    rows = []
    names = {}
    files = 0
    newest = None
    for folder in folders:
        listed = _slices(folder)
        files += len(listed)
        for _key, path in listed:
            try:
                stamp = os.path.getmtime(extended_path(path))
            except OSError as exc:
                note_read_problem(path, exc.__class__.__name__)
                continue
            if newest is None or stamp > newest:
                newest = stamp
        slices.extend(listed)
        try:
            rows.extend(_transcripts(folder))
        except Exception as exc:
            note_read_problem(folder, exc.__class__.__name__)
        try:
            names.update(roster_names(folder))
        except Exception as exc:
            note_read_problem(folder, exc.__class__.__name__)
    _scan["files"] = files
    _scan["newest"] = newest
    return slices, rows, names


def _row_for(rows, account, agent_id):
    matches = [row for row in rows if row["agent_id"] == agent_id and (account is None or row["account"] == account)]
    if account is None and len(matches) == 1:
        return matches[0]
    for row in matches:
        if row["account"] == account:
            return row
    return None


def _newest_message_ms(row):
    newest = 0
    for entry in row.get("entries") or []:
        if isinstance(entry, dict) and isinstance(entry.get("timestampMs"), (int, float)):
            newest = max(newest, entry["timestampMs"])
    return newest


def _live_row(rows):
    """The transcript whose file changed last. A new reply updates that file."""
    if not rows:
        return None
    return max(rows, key=lambda row: (row.get("stamp") or 0, _newest_message_ms(row)))


# What the reader last decided. Logged only when it changes.
_open_choice = {"line": None, "selection": None}


def _remember_open(names, row, how):
    if row is None:
        bot = "uncertain"
    else:
        bot = names.get(row.get("agent_id")) or row.get("agent_id") or "unknown"
    line = "open chat: %s (%s)" % (bot, how)
    _open_choice["line"] = line
    return line


def open_chat_line():
    """The latest open-chat decision, including why."""
    return _open_choice["line"]


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
    for key, path in slices:
        match = ROSTER_SLICE.match(key)
        if not match or match.group(1) != account:
            continue
        picked = _roster_selected_id([(key, path)], account, known)
        if picked:
            hits.append((_mtime(path), picked, account, "strong"))
    strong = [hit for hit in hits if hit[3] == "strong"]
    weak = [hit for hit in hits if hit[3] == "weak"]
    ranked = strong or weak
    ranked.sort()
    selection_mtime = ranked[-1][0] if ranked else None
    selection_id = ranked[-1][1] if ranked else None
    if ranked and ranked[-1][3] == "weak":
        live = _live_row(scoped)
        # Another device's last-opened slice must not hide the chat that just changed.
        if live and live["agent_id"] != selection_id and (live.get("stamp") or 0) >= (selection_mtime or 0):
            selection_mtime = None
            selection_id = None
    _open_choice["selection"] = selection_id if strong else None
    names = _names

    def choose(row, how):
        _remember_open(names, row, how)
        return row

    opened = _focused_opens(scoped)
    if len(opened) == 1 and (selection_mtime is None or opened[0]["stamp"] > selection_mtime + 0.5):
        chosen = opened[0]
        live = _live_row(scoped)
        # A sync rewrites an idle chat and makes it look opened. If a different
        # chat's file is newer, that is the conversation on this screen.
        # A strong selection that names this opened chat still wins: a background
        # bot's reply must not take the window.
        if (live and live["path"] != chosen["path"]
                and (live.get("stamp") or 0) > (chosen.get("stamp") or 0)
                and _open_choice.get("selection") != chosen["agent_id"]):
            return choose(live, "most recently active")
        return choose(chosen, "opened file")
    if selection_id:
        chosen = _row_for(scoped, account, selection_id)
        if chosen is not None:
            return choose(chosen, "selection")
    selected = _roster_selected_id(slices, account, known)
    chosen = _row_for(scoped, account, selected) if selected else None
    if chosen is not None:
        _open_choice["selection"] = selected
        return choose(chosen, "selection")
    if len(scoped) == 1:
        return choose(scoped[0], "only chat")
    return choose(None, "uncertain")


def latest_replay(lines):
    """The reply Back plays for the chat that is open. None when that chat is unknown."""
    if not lines:
        return None
    return lines[-1]


def _bot_names(names, bot):
    labels = list(names.values())
    if bot:
        labels.append(bot)
    return sorted(set(labels), key=len, reverse=True)


def _speech_lines(transcript, names):
    """(lines, key lists, bot) for one saved transcript."""
    agent_id = transcript["agent_id"]
    bot = plain_label(names.get(agent_id) or "") or "Bot"
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
    return lines, keylists, bot


def _unseen_pairs(seen, lines, keylists):
    found = []
    for line, keys in zip(lines, keylists):
        if any(key in seen for key in keys):
            continue
        found.append((keys, line))
    return found


def reply_snapshot(directory, window_titles=None, directories=None):
    """(lines, bot names, key lists, active file) for the open chat.

    key lists identify replies without using their position. active file is
    the transcript path, or None when there is no chat to follow.
    window_titles are ignored. Every call re-reads the stores. None for the
    active file means the open chat is not known, so Back stays quiet.
    The watcher uses watch_snapshot, which can still speak one new reply.
    """
    folders = _store_list(directory, directories)
    names = {}
    for folder in folders:
        names.update(roster_names(folder))
    transcript = active_transcript(directory, window_titles=window_titles, directories=directories)
    if transcript is None:
        return [], _bot_names(names, ""), [], None
    lines, keylists, bot = _speech_lines(transcript, names)
    return lines, _bot_names(names, bot), keylists, transcript["path"]


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
    order does not come back as a new reply. Two new replies in one file
    are both returned, in order.
    """
    fresh = []
    for line, keys in zip(lines, keylists):
        if any(key in seen for key in keys):
            seen.update(keys)
            continue
        seen.update(keys)
        fresh.append(line)
    return fresh


def merge_open_replies(history, seen, lines, keylists):
    """Append every new reply in the open chat, in order.

    A second reply written into the same file is not dropped because the
    first one was new too. Returns the lines that were added.
    """
    fresh = unseen_lines(seen, lines, keylists)
    history.extend(fresh)
    return fresh


def every_reply_keylists(directory, directories=None):
    """Keys for every reply already on disk. Launch treats them as history."""
    _slices, rows, names = _load_stores(_store_list(directory, directories))
    keylists = []
    for row in rows:
        _lines, keys, _bot = _speech_lines(row, names)
        keylists.extend(keys)
    return keylists


def skip_log(reason, preview=""):
    """Debug line for a new reply that was not spoken."""
    text = "skip new reply: %s" % reason
    preview = " ".join(str(preview or "").split())
    if preview:
        text += " | " + preview[:80]
    return text


def watch_snapshot(directory, window_titles=None, directories=None, seen=None, follow_path=None):
    """(lines, bot names, key lists, path, skipped) for automatic reading.

    skipped is a list of (keys, reason, preview) for new replies left unspoken.

    A known open chat wins. When the files no longer say which chat is on
    screen, keep follow_path so a reply in the chat already being read is
    still spoken. That happens when a reply lands: the file time matches the
    new message, so the 'just opened' signal goes away. With no chat to keep,
    one transcript that gained a reply is spoken. Several new replies and no
    open chat stay quiet, and each one is listed in skipped.
    """
    seen = seen if seen is not None else set()
    folders = _store_list(directory, directories)
    _slices, rows, names = _load_stores(folders)
    transcript = active_transcript(directory, window_titles=window_titles, directories=directories)

    def pack(row):
        lines, keylists, bot = _speech_lines(row, names)
        return lines, _bot_names(names, bot), keylists, row["path"]

    def fresh_map():
        found = []
        pairs = {}
        for row in rows:
            lines, keylists, _bot = _speech_lines(row, names)
            unseen = _unseen_pairs(seen, lines, keylists)
            if unseen:
                found.append(row)
                pairs[row["path"]] = unseen
        return found, pairs

    if transcript is not None:
        skipped = []
        for row in rows:
            if row["path"] == transcript["path"]:
                continue
            lines, keylists, _bot = _speech_lines(row, names)
            for keys, line in _unseen_pairs(seen, lines, keylists):
                skipped.append((keys, "not the open chat", line))
        lines, bot_names, keylists, path = pack(transcript)
        return lines, bot_names, keylists, path, skipped

    followed = next((row for row in rows if follow_path and row["path"] == follow_path), None)
    fresh_rows, pairs = fresh_map()
    if followed is not None:
        skipped = []
        for row in fresh_rows:
            if row["path"] == followed["path"]:
                continue
            for keys, line in pairs[row["path"]]:
                skipped.append((keys, "not the open chat", line))
        _remember_open(names, followed, "kept")
        lines, bot_names, keylists, path = pack(followed)
        return lines, bot_names, keylists, path, skipped
    if len(fresh_rows) == 1:
        _remember_open(names, fresh_rows[0], "most recently active")
        lines, bot_names, keylists, path = pack(fresh_rows[0])
        return lines, bot_names, keylists, path, []
    _remember_open(names, None, "uncertain")
    skipped = []
    for row in fresh_rows:
        for keys, line in pairs[row["path"]]:
            skipped.append((keys, "open chat unclear", line))
    return [], _bot_names(names, ""), [], None, skipped
