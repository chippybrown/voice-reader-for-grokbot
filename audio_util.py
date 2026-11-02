# Shared WAV helpers for Piper pitch and the xAI speech response.
import wave

import grok_store


def pitch_ratio(pitch):
    """Slider -10..10 to a playback-rate ratio. 0 keeps the original pitch."""
    return 2 ** ((float(pitch) * 0.6) / 12.0)


def write_pcm_wav(path, pcm, rate=24000):
    """24 kHz 16-bit mono PCM, the shape xAI's speech API returns."""
    params = wave._wave_params(1, 2, rate, len(pcm) // 2, "NONE", "not compressed")
    with wave.open(grok_store.extended_path(path), "wb") as handle:
        handle.setparams(params)
        handle.writeframes(pcm)
    seconds = len(pcm) / float(rate * 2)
    return params, pcm, seconds


def scale_wav_rate(path, ratio):
    """Raise or lower pitch by playing the same samples at another rate.

    Returns (params, frames, seconds) for the file as it will be heard.
    """
    with wave.open(grok_store.extended_path(path), "rb") as handle:
        params = handle.getparams()
        frames = handle.readframes(handle.getnframes())
    if abs(ratio - 1.0) < 0.001:
        seconds = params.nframes / float(params.framerate or 1)
        return params, frames, seconds
    rate = max(1, int(params.framerate * ratio))
    shifted = params._replace(framerate=rate)
    with wave.open(grok_store.extended_path(path), "wb") as handle:
        handle.setparams(shifted)
        handle.writeframes(frames)
    seconds = params.nframes / float(rate)
    return shifted, frames, seconds
