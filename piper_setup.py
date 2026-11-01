# Download Piper and the free English voices into the app's own folder.
# Standard library only, so the first launch needs no extra install and no admin.
import io
import os
import shutil
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

RELEASE = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2"
VOICES_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en"
# Female: Jenny, Amy, Lessac, Alba, Cori, LJ Speech. Male: Ryan, Alan, Joe.
VOICE_PATHS = (
    "en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium",
    "en_US/amy/medium/en_US-amy-medium",
    "en_US/lessac/medium/en_US-lessac-medium",
    "en_GB/alba/medium/en_GB-alba-medium",
    "en_GB/cori/medium/en_GB-cori-medium",
    "en_US/ljspeech/high/en_US-ljspeech-high",
    "en_US/ryan/medium/en_US-ryan-medium",
    "en_GB/alan/medium/en_GB-alan-medium",
    "en_US/joe/medium/en_US-joe-medium",
)
ATTEMPTS = 3


def voice_stem(path):
    return path.rsplit("/", 1)[-1]


def voice_label(path):
    stem = voice_stem(path)
    key = stem.split("-")[1] if "-" in stem else stem
    return {"jenny_dioco": "Jenny", "ljspeech": "LJ Speech"}.get(key, key.replace("_", " ").title())


def binary_spec(system, machine):
    """(url, filename inside the piper folder, archive kind) or None."""
    system = (system or "").lower()
    machine = (machine or "").lower()
    if system.startswith("win"):
        if machine in ("amd64", "x86_64"):
            return RELEASE + "/piper_windows_amd64.zip", "piper.exe", "zip"
        return None
    if machine in ("aarch64", "arm64"):
        arch = "aarch64"
    elif machine in ("x86_64", "amd64"):
        arch = "x86_64"
    else:
        return None
    return RELEASE + "/piper_linux_%s.tar.gz" % arch, "piper", "tar"


def _present(path):
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def missing_items(piper_dir, system, machine):
    """Files still needed: (label, url, dest, archive kind or None)."""
    needed = []
    spec = binary_spec(system, machine)
    if spec:
        url, filename, kind = spec
        dest = os.path.join(piper_dir, filename)
        if not _present(dest):
            needed.append(("Piper", url, dest, kind))
    for path in VOICE_PATHS:
        stem = voice_stem(path)
        label = voice_label(path)
        for ext in (".onnx", ".onnx.json"):
            dest = os.path.join(piper_dir, stem + ext)
            if not _present(dest):
                needed.append((label, VOICES_BASE + "/" + path + ext, dest, None))
    return needed


def preferred_index(labels, saved):
    """Saved choice, otherwise Jenny, otherwise Amy, otherwise the first voice."""
    saved = (saved or "").strip()
    if saved:
        for index, label in enumerate(labels):
            if label == saved:
                return index
    for prefix in ("Jenny", "Amy"):
        for index, label in enumerate(labels):
            if label.startswith(prefix):
                return index
    return 0


def _extract(archive, piper_dir, kind):
    parent = os.path.dirname(os.path.abspath(piper_dir))
    if kind == "zip":
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            for name in names:
                if name.startswith("/") or ".." in name.replace("\\", "/").split("/"):
                    raise RuntimeError("unsafe archive")
            bundle.extractall(parent)
    else:
        with tarfile.open(archive) as bundle:
            for member in bundle.getmembers():
                if member.name.startswith("/") or ".." in member.name.split("/"):
                    raise RuntimeError("unsafe archive")
            bundle.extractall(parent)


def _fetch(url, dest, urlopen):
    opener = urlopen or urllib.request.urlopen
    last = None
    partial = dest + ".partial"
    for attempt in range(ATTEMPTS):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "GrokbotVoice"})
            with opener(request, timeout=120) as response, open(partial, "wb") as out:
                shutil.copyfileobj(response, out)
            os.replace(partial, dest)
            return
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            try:
                os.remove(partial)
            except OSError:
                pass
            if attempt + 1 < ATTEMPTS:
                time.sleep(0.2 * (attempt + 1))
    raise last


def ensure(piper_dir, system, progress, machine=None, urlopen=None):
    """Download anything missing. True when the voices are ready.

    progress(message) is called for each file. An offline machine keeps the
    voices it already has and returns False instead of raising.
    """
    machine = machine or __import__("platform").machine()
    os.makedirs(piper_dir, exist_ok=True)
    needed = missing_items(piper_dir, system, machine)
    if not needed:
        return True
    total = len(needed)
    for index, (label, url, dest, kind) in enumerate(needed, 1):
        progress("Downloading %s (%d/%d)" % (label, index, total))
        try:
            if kind:
                archive = dest + ".download"
                _fetch(url, archive, urlopen)
                _extract(archive, piper_dir, kind)
                try:
                    os.remove(archive)
                except OSError:
                    pass
                if not _present(dest):
                    raise RuntimeError("Piper did not unpack")
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                _fetch(url, dest, urlopen)
        except Exception:
            progress("Piper voices unavailable. Using built-in voices.")
            return False
    return True
