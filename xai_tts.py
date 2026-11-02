# Build an xAI text-to-speech request and read the audio it returns.
# The key never belongs in a log line.
import base64
import io
import json
import re
import wave

ENDPOINT = "https://api.x.ai/v1/tts"
MAX_CHARS = 60000
_VOICE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def spoken_text(text):
    """Text the speech API will accept. Quotes and ellipsis are normalized."""
    raw = str(text or "")
    raw = (raw.replace("\u201c", '"').replace("\u201d", '"')
              .replace("\u2018", "'").replace("\u2019", "'")
              .replace("\u2026", "...").replace("\u2014", ", ").replace("\u2013", "-"))
    kept = []
    for char in raw:
        if char in "\n\t":
            kept.append(" ")
        elif ord(char) >= 32:
            kept.append(char)
    spoken = " ".join("".join(kept).split())
    if len(spoken) > MAX_CHARS:
        spoken = spoken[:MAX_CHARS].rsplit(" ", 1)[0]
    return spoken


def payload(text, voice_id, speed):
    """JSON body for POST /v1/tts. Language is a BCP-47 code. Audio is WAV."""
    spoken = spoken_text(text)
    if not spoken:
        raise ValueError("nothing to speak")
    try:
        rate = float(speed)
    except (TypeError, ValueError):
        rate = 1.0
    rate = max(0.7, min(1.5, rate))
    voice = str(voice_id or "").strip()
    if not _VOICE.match(voice):
        voice = "eve"
    return {
        "text": spoken,
        "voice_id": voice,
        "language": "en",
        "speed": rate,
        "output_format": {"codec": "wav", "sample_rate": 24000},
    }


def error_log(status, body):
    """One log line. The API key is not included."""
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    text = " ".join(str(body or "").split())
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", text)
    text = re.sub(r"xai-[A-Za-z0-9_-]+", "[redacted]", text)
    if len(text) > 300:
        text = text[:300]
    return "Grok voice problem, using a local voice: HTTP %s %s" % (status, text)


def pcm_bytes(body, content_type=""):
    """PCM frames from a raw body, a WAV body, or a JSON envelope."""
    raw = body or b""
    kind = content_type or ""
    if raw[:1] == b"{" or "json" in kind.lower():
        parsed = json.loads(raw.decode("utf-8"))
        raw = base64.b64decode(parsed["audio"])
    if raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            channels = handle.getnchannels()
            width = handle.getsampwidth()
        if channels == 2 and width == 2:
            mono = bytearray()
            for index in range(0, len(frames), 4):
                left = int.from_bytes(frames[index:index + 2], "little", signed=True)
                right = int.from_bytes(frames[index + 2:index + 4], "little", signed=True)
                mixed = max(-32768, min(32767, (left + right) // 2))
                mono.extend(mixed.to_bytes(2, "little", signed=True))
            return bytes(mono)
        return frames
    return raw
