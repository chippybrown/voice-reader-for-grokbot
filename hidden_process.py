# Start a program without a console window on Windows.
# piper.exe is a console program. A windowed app that launches it the
# ordinary way gets a flashing terminal on every spoken line.
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0


class _HideInfo(object):
    """Stand-in when this interpreter has no subprocess.STARTUPINFO."""

    def __init__(self):
        self.dwFlags = 0
        self.wShowWindow = 0


def _startupinfo():
    maker = getattr(subprocess, "STARTUPINFO", None)
    if maker is None:
        return _HideInfo()
    return maker()


def hidden_kwargs(kwargs, windows=None):
    """Add CREATE_NO_WINDOW and a hidden window. Other systems are unchanged."""
    if windows is None:
        windows = sys.platform == "win32"
    if not windows:
        return kwargs
    updated = dict(kwargs)
    updated["creationflags"] = int(updated.get("creationflags") or 0) | CREATE_NO_WINDOW
    info = updated.get("startupinfo") or _startupinfo()
    info.dwFlags |= STARTF_USESHOWWINDOW
    info.wShowWindow = SW_HIDE
    updated["startupinfo"] = info
    return updated


def run(args, **kwargs):
    return subprocess.run(args, **hidden_kwargs(kwargs))


def popen(args, **kwargs):
    return subprocess.Popen(args, **hidden_kwargs(kwargs))
