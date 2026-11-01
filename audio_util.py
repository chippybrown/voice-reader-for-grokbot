# Shared WAV helpers for Piper pitch, the xAI speech response, and mute chimes.
import math
import struct
import wave


def pitch_ratio(pitch):
    """Slider -10..10 to a playback-rate ratio. 0 keeps the original pitch."""
    return 2 ** ((float(pitch) * 0.6) / 12.0)


def write_pcm_wav(path, pcm, rate=24000):
    """24 kHz 16-bit mono PCM, the shape xAI's speech API returns."""
    params = wave._wave_params(1, 2, rate, len(pcm) // 2, "NONE", "not compressed")
    with wave.open(path, "wb") as handle:
        handle.setparams(params)
        handle.writeframes(pcm)
    seconds = len(pcm) / float(rate * 2)
    return params, pcm, seconds


def scale_wav_rate(path, ratio):
    """Raise or lower pitch by playing the same samples at another rate.

    Returns (params, frames, seconds) for the file as it will be heard.
    """
    with wave.open(path, "rb") as handle:
        params = handle.getparams()
        frames = handle.readframes(handle.getnframes())
    if abs(ratio - 1.0) < 0.001:
        seconds = params.nframes / float(params.framerate or 1)
        return params, frames, seconds
    rate = max(1, int(params.framerate * ratio))
    shifted = params._replace(framerate=rate)
    with wave.open(path, "wb") as handle:
        handle.setparams(shifted)
        handle.writeframes(frames)
    seconds = params.nframes / float(rate)
    return shifted, frames, seconds


def write_chime(path, freqs, ms=150, rate=16000):
    """A short tone, or a few tones in a row. Used when the mic is muted or unmuted."""
    frames = bytearray()
    for freq in freqs:
        count = int(rate * ms / 1000)
        for i in range(count):
            fade = min(1.0, i / max(1, rate * 0.02), (count - i) / max(1, rate * 0.05))
            sample = int(fade * 0.35 * 32767 * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<h", max(-32767, min(32767, sample)))
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
