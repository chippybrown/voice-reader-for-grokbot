# Spoken Play and Stop. No audio libraries here, so the rules can be tested
# without a microphone or Vosk.
import re

# The name in front is the wake name. These two tails are the only commands.
COMMAND_TAILS = (
    ("speak", "speak"),
    ("quiet", "quiet"),
)
MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_URL = "https://alphacephei.com/vosk/models/%s.zip" % MODEL_NAME
# After our own voice stops, ignore the tail so it cannot start another read.
ECHO_HOLD = 0.6


def phrases_for(name):
    """{'larry speak': 'speak', 'larry quiet': 'quiet'} for the wake name."""
    name = " ".join((name or "").lower().split())
    if not name:
        return {}
    return {"%s %s" % (name, tail): action for tail, action in COMMAND_TAILS}


def grammar_for(name):
    """Vosk grammar limited to this name's two phrases, plus [unk]."""
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


def _name_matches(tokens, name_words, exact):
    if len(tokens) != len(name_words):
        return False
    if exact:
        return list(tokens) == list(name_words)
    return all(_close_word(heard, wanted) for heard, wanted in zip(tokens, name_words))


def phrase_action(text, name, exact_name=False):
    """Find speak or quiet inside a noisy result. The last phrase wins.

    '[unk]' tokens are dropped first. The name is the words just before
    speak or quiet. exact_name requires those words to match exactly.
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
        if not _name_matches(tokens[start:start + width], name_words, exact_name):
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
    While a reply is being read, only an exact wake name followed by quiet
    is accepted. Speak is ignored then, and the recognizer should be reset
    so a half-heard echo cannot finish later.
    """
    if speaking:
        if phrase_action(text, name, exact_name=True) == "quiet":
            return "quiet", now + ECHO_HOLD, True
        return None, quiet_until, True
    if now < quiet_until:
        return None, quiet_until, False
    action = phrase_action(text, name)
    if not action:
        return None, quiet_until, False
    return action, now + ECHO_HOLD, False
