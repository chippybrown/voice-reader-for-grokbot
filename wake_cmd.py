# Wake phrases and the helpers that decide whose microphone to close.
# No audio libraries here, so the rules can be tested without a mic or Vosk.
import os

# The small English Vosk model has no "unmute". These phrases use words it knows.
PHRASES = {
    "moya sleep": "mute",
    "moya mute": "mute",
    "moya wake": "unmute",
    "moya wake up": "unmute",
    "moya listen": "unmute",
    "moya un mute": "unmute",
}
GRAMMAR = '["moya sleep", "moya mute", "moya wake", "moya wake up", "moya listen", "moya un mute", "[unk]"]'
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


def phrase_action(text):
    """Find a command inside a noisy Vosk result. The last phrase wins.

    '[unk]' tokens are dropped first. 'moya mute moya wake' unmutes.
    A phrase has to be contiguous words, so 'moya please mute' is ignored.
    """
    tokens = [token for token in (text or "").lower().split() if token != "[unk]"]
    if not tokens:
        return None
    phrases = sorted(((phrase.split(), action) for phrase, action in PHRASES.items()), key=lambda item: len(item[0]), reverse=True)
    last_action = None
    last_end = -1
    for start in range(len(tokens)):
        for words, action in phrases:
            end = start + len(words)
            if tokens[start:end] == words and end >= last_end:
                last_action = action
                last_end = end
                break
    return last_action


def consider_phrase(text, speaking, now, quiet_until):
    """Decide what a recognizer result means.

    Returns (action or None, new quiet_until, reset_recognizer).
    While we are speaking, the result is thrown away and the recognizer
    should be reset so a half-heard echo cannot finish later.
    """
    if speaking:
        return None, quiet_until, True
    if now < quiet_until:
        return None, quiet_until, False
    action = phrase_action(text)
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
