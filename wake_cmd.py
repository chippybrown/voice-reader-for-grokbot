# Wake phrases and the helpers that decide whose microphone to close.
# No audio libraries here, so the rules can be tested without a mic or Vosk.
import os
import re

# The small English model has no single word "unmute". These tails use words it knows.
# The name in front is whoever the user set as the wake name.
COMMAND_TAILS = (
    ("sleep", "mute"),
    ("mute", "mute"),
    ("wake up", "unmute"),
    ("listen", "unmute"),
    ("un mute", "unmute"),
    ("wake", "unmute"),
)
MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = "https://alphacephei.com/vosk/models/%s.zip" % MODEL_NAME
# Ignore the mic briefly after we speak or chime, so the tail cannot retrigger.
ECHO_HOLD = 0.6

# Grok Bot's own program names. "Grokbot Voice" is us and must not match.
_BOT_BASENAMES = {
    "grok bot",
    "grok bot.exe",
    "grok-bot",
    "grok-bot.exe",
    "grok_bot",
    "grok_bot.exe",
    "sand",
    "sand.exe",
}


def phrases_for(name):
    """{'larry mute': 'mute', ...} for the wake name."""
    name = " ".join((name or "").lower().split())
    if not name:
        return {}
    return {"%s %s" % (name, tail): action for tail, action in COMMAND_TAILS}


def grammar_for(name):
    """Vosk grammar limited to this name's phrases, plus [unk]."""
    phrases = sorted(phrases_for(name), key=lambda phrase: len(phrase.split()), reverse=True)
    body = ", ".join('"%s"' % phrase for phrase in phrases)
    if body:
        body += ", "
    return "[" + body + '"[unk]"]'


def resolve_wake_name(override, chief, primary, active):
    """First non-empty of the settings override, chief of staff, roster, then open chat."""
    for value in (override, chief, primary, active):
        text = " ".join(str(value or "").split())
        if text:
            return text
    return ""


def name_words_missing(log_text, name):
    """Words of the wake name that Vosk reported as missing from its vocabulary."""
    missing = set(re.findall(r"Ignoring word missing in vocabulary: '([^']+)'", log_text or ""))
    return [word for word in (name or "").lower().split() if word in missing]


def _edit_distance(left, right):
    if left == right:
        return 0
    previous = list(range(len(right) + 1))
    for i, ca in enumerate(left, 1):
        current = [i]
        for j, cb in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _phonetic(word):
    letters = "".join(char for char in (word or "").lower() if char.isalpha())
    if not letters:
        return ""
    rest = "".join(char for char in letters[1:] if char not in "aeiouy")
    folded = letters[0] + rest
    squashed = folded[0]
    for char in folded[1:]:
        if char != squashed[-1]:
            squashed += char
    return squashed


def _close_word(heard, wanted):
    if heard == wanted:
        return True
    limit = 1 if len(wanted) <= 6 else 2
    if _edit_distance(heard, wanted) <= limit:
        return True
    return bool(_phonetic(wanted)) and _phonetic(heard) == _phonetic(wanted)


def _name_matches(tokens, name_words):
    if len(tokens) != len(name_words):
        return False
    return all(_close_word(heard, wanted) for heard, wanted in zip(tokens, name_words))


def phrase_action(text, name):
    """Find a command inside a noisy result. The last phrase wins.

    '[unk]' tokens are dropped first. The name is an exact word sequence, or a
    close phonetic or edit-distance match, followed by mute, sleep, or wake.
    """
    tokens = [token for token in (text or "").lower().split() if token != "[unk]"]
    name_words = (name or "").lower().split()
    if not tokens or not name_words:
        return None
    tails = sorted(((tail.split(), action) for tail, action in COMMAND_TAILS), key=lambda item: len(item[0]), reverse=True)
    last_action = None
    last_end = -1
    width = len(name_words)
    for start in range(len(tokens)):
        if not _name_matches(tokens[start:start + width], name_words):
            continue
        for words, action in tails:
            end = start + width + len(words)
            if tokens[start + width:end] == words and end >= last_end:
                last_action = action
                last_end = end
                break
    return last_action


def consider_phrase(text, speaking, now, quiet_until, name):
    """Decide what a recognizer result means.

    Returns (action or None, new quiet_until, reset_recognizer).
    While we are speaking, the result is thrown away and the recognizer
    should be reset so a half-heard echo cannot finish later.
    """
    if speaking:
        return None, quiet_until, True
    if now < quiet_until:
        return None, quiet_until, False
    action = phrase_action(text, name)
    if not action:
        return None, quiet_until, False
    return action, now + ECHO_HOLD, False


def is_our_app(name):
    lowered = (name or "").lower()
    return "grokbot voice" in lowered or "grokbot-voice" in lowered or "voice_listener" in lowered


def is_grok_bot_name(name):
    """True for the Grok Bot app, false for Grokbot Voice and unrelated programs."""
    if not name or is_our_app(name):
        return False
    base = os.path.basename(name.replace("\\", "/")).lower()
    if base in _BOT_BASENAMES:
        return True
    compact = " ".join(base.replace("-", " ").replace("_", " ").replace(".exe", "").split())
    return compact == "grok bot" or compact == "sand"


def consent_key_name(exe_path):
    """Windows stores a desktop app's mic permission under this registry name."""
    path = os.path.normpath(exe_path).replace("/", "\\")
    return path.replace("\\", "#")


def parse_source_outputs(text):
    """pactl list source-outputs -> [{id, name, binary}, ...]."""
    blocks = []
    current = None
    for line in (text or "").splitlines():
        if line.startswith("Source Output #"):
            if current:
                blocks.append(current)
            current = {"id": line.split("#", 1)[1].strip(), "name": "", "binary": ""}
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("application.name ="):
            current["name"] = _unquote(stripped.split("=", 1)[1].strip())
        elif stripped.startswith("application.process.binary ="):
            current["binary"] = _unquote(stripped.split("=", 1)[1].strip())
    if current:
        blocks.append(current)
    return blocks


def grok_bot_source_ids(text):
    ids = []
    for block in parse_source_outputs(text):
        if is_grok_bot_name(block["name"]) or is_grok_bot_name(block["binary"]):
            ids.append(block["id"])
    return ids


def _unquote(value):
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value
