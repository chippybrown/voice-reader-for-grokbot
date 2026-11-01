# Offline "<name> mute" / "<name> wake" listener. The model is downloaded once.
import json
import os
import queue
import shutil
import threading
import time
import urllib.request
import zipfile

import wake_cmd


def _capture_stderr(action):
    """Run action and return text the C library wrote to stderr."""
    import os
    import tempfile
    saved = os.dup(2)
    handle = tempfile.TemporaryFile()
    try:
        os.dup2(handle.fileno(), 2)
        action()
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        handle.seek(0)
        text = handle.read().decode("utf-8", "ignore")
        handle.close()
    return text


class VoiceListener:
    def __init__(self, config_dir, on_command, is_speaking, log, wake_name):
        self.config_dir = config_dir
        self.on_command = on_command
        self.is_speaking = is_speaking
        self.log = log
        self.wake_name = wake_name
        self.running = False
        self.thread = None
        self.quiet_until = 0.0
        self._stream = None
        self._heard_name = ""

    def start(self):
        if self.thread and self.thread.is_alive():
            self.running = True
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, name="voice-commands", daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass

    def _run(self):
        try:
            model_path = self._ensure_model()
        except Exception as exc:
            self.log("voice commands: could not get the speech model: %r" % (exc,))
            return
        if not self.running or not model_path:
            return
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
            import sounddevice as sd
        except Exception as exc:
            self.log("voice commands need the vosk and sounddevice packages: %r" % (exc,))
            return
        SetLogLevel(-1)
        try:
            model = Model(model_path)
            recognizer = self._recognizer_for(model)
            audio_q = queue.Queue()

            def callback(indata, frames, time_info, status):
                if self.running:
                    audio_q.put(bytes(indata))

            with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1, callback=callback) as stream:
                self._stream = stream
                self.log("voice commands are listening")
                reset_next = False
                while self.running:
                    try:
                        data = audio_q.get(timeout=0.3)
                    except queue.Empty:
                        continue
                    speaking = False
                    try:
                        speaking = bool(self.is_speaking())
                    except Exception:
                        speaking = False
                    if speaking:
                        reset_next = True
                        recognizer.Reset()
                        continue
                    fresh = self._recognizer_for(model)
                    if fresh is not recognizer:
                        recognizer = fresh
                    if reset_next:
                        reset_next = False
                        recognizer.Reset()
                        self.quiet_until = time.time() + wake_cmd.ECHO_HOLD
                        continue
                    if not recognizer.AcceptWaveform(data):
                        continue
                    try:
                        heard = json.loads(recognizer.Result()).get("text") or ""
                    except Exception:
                        heard = ""
                    action, self.quiet_until, reset = wake_cmd.consider_phrase(
                        heard, False, time.time(), self.quiet_until, self._heard_name)
                    if reset:
                        recognizer.Reset()
                    if action and self.running:
                        self.on_command(action)
        except Exception as exc:
            self.log("voice commands stopped: %r" % (exc,))
        finally:
            self._stream = None

    def _recognizer_for(self, model):
        from vosk import KaldiRecognizer
        name = ""
        try:
            name = self.wake_name() or ""
        except Exception:
            name = ""
        if name == self._heard_name and getattr(self, "_recognizer", None) is not None:
            return self._recognizer
        self._heard_name = name
        grammar = wake_cmd.grammar_for(name)
        warning = _capture_stderr(lambda: KaldiRecognizer(model, 16000, grammar))
        missing = wake_cmd.name_words_missing(warning, name)
        if missing:
            self.log("The speech model does not know %s. Voice commands will listen for a similar sound followed by mute or wake. A simpler wake name in Settings is easier to hear." % ", ".join(missing))
            recognizer = KaldiRecognizer(model, 16000)
        else:
            recognizer = KaldiRecognizer(model, 16000, grammar)
            self.log("voice commands listen for %s" % name)
        self._recognizer = recognizer
        return recognizer

    def _ensure_model(self):
        dest = os.path.join(self.config_dir, wake_cmd.MODEL_NAME)
        if os.path.isdir(os.path.join(dest, "conf")):
            return dest
        if not self.running:
            return None
        os.makedirs(self.config_dir, exist_ok=True)
        self.log("Downloading the small voice-command model (about 40 MB). This happens once.")
        zip_path = dest + ".zip"
        request = urllib.request.Request(wake_cmd.MODEL_URL, headers={"User-Agent": "GrokbotVoice"})
        with urllib.request.urlopen(request, timeout=120) as response, open(zip_path, "wb") as out:
            shutil.copyfileobj(response, out)
        if not self.running:
            return None
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(self.config_dir)
        try:
            os.remove(zip_path)
        except OSError:
            pass
        if not os.path.isdir(os.path.join(dest, "conf")):
            raise RuntimeError("voice model did not unpack")
        self.log("Voice-command model is ready")
        return dest
