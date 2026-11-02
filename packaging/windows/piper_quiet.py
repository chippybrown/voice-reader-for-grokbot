# Speak one line with the frozen app through a console-subsystem piper.exe.
# A missing CREATE_NO_WINDOW shows up as a ConsoleWindowClass or conhost window.
import argparse
import os
import subprocess
import sys
import time

STUB = r"""
using System;
using System.IO;
using System.Text;
using System.Threading;

class PiperStub {
    static string Plain(string path) {
        if (path.StartsWith(@"\\?\UNC\")) return @"\\" + path.Substring(8);
        if (path.StartsWith(@"\\?\")) return path.Substring(4);
        return path;
    }

    static int Main(string[] args) {
        string output = "out.wav";
        for (int i = 0; i < args.Length - 1; i++) {
            if (args[i] == "--output_file") output = args[i + 1];
        }
        string here = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
        File.WriteAllText(Path.Combine(here, "piper-ran.txt"), "ran");
        Thread.Sleep(2000);
        WriteWav(Plain(output));
        return 0;
    }

    static void WriteWav(string path) {
        int rate = 22050;
        short[] samples = new short[rate / 5];
        for (int i = 0; i < samples.Length; i++)
            samples[i] = (short)(i % 20 < 10 ? 4000 : -4000);
        using (var stream = new FileStream(path, FileMode.Create, FileAccess.Write))
        using (var writer = new BinaryWriter(stream)) {
            int dataBytes = samples.Length * 2;
            writer.Write(Encoding.ASCII.GetBytes("RIFF"));
            writer.Write(36 + dataBytes);
            writer.Write(Encoding.ASCII.GetBytes("WAVEfmt "));
            writer.Write(16);
            writer.Write((short)1);
            writer.Write((short)1);
            writer.Write(rate);
            writer.Write(rate * 2);
            writer.Write((short)2);
            writer.Write((short)16);
            writer.Write(Encoding.ASCII.GetBytes("data"));
            writer.Write(dataBytes);
            foreach (short sample in samples) writer.Write(sample);
        }
    }
}
"""


def compile_stub(dest):
    folder = os.path.dirname(dest)
    source = os.path.join(folder, "piper_stub.cs")
    with open(source, "w", encoding="utf-8") as handle:
        handle.write(STUB)
    compiler = None
    for candidate in (
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
    ):
        if os.path.isfile(candidate):
            compiler = candidate
            break
    if not compiler:
        raise SystemExit("csc.exe was not found")
    result = subprocess.run([compiler, "/nologo", "/t:exe", "/out:" + dest, source], capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
        raise SystemExit("piper stub did not compile")


def _bind():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return user32, kernel32, enum_proc


def visible_windows():
    user32, _kernel32, enum_proc = _bind()
    found = []

    def collect(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            found.append(int(hwnd))
        return True

    callback = enum_proc(collect)
    user32.EnumWindows(callback, 0)
    return found


def window_owner(hwnd):
    user32, kernel32, _enum = _bind()
    pid = __import__("ctypes").wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, __import__("ctypes").byref(pid))
    class_name = __import__("ctypes").create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_name, 256)
    image = ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if handle:
        buf = __import__("ctypes").create_unicode_buffer(512)
        size = __import__("ctypes").wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, __import__("ctypes").byref(size)):
            image = buf.value
        kernel32.CloseHandle(handle)
    return class_name.value, os.path.basename(image), pid.value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--workdir", default="")
    args = parser.parse_args()
    work = args.workdir or os.path.join(os.environ.get("TEMP", "."), "grokbot-piper-quiet")
    if os.path.isdir(work):
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    appdata = os.path.join(work, "roaming")
    local = os.path.join(work, "local")
    temp = os.path.join(work, "temp")
    piper = os.path.join(appdata, "Grok Voice", "piper")
    os.makedirs(piper)
    os.makedirs(local)
    os.makedirs(temp)
    compile_stub(os.path.join(piper, "piper.exe"))
    with open(os.path.join(piper, "en_US-quietpiper-medium.onnx"), "wb") as handle:
        handle.write(b"onnx")
    with open(os.path.join(appdata, "Grok Reader voice.txt"), "w", encoding="utf-8") as handle:
        handle.write("Quietpiper (natural)")
    before = set(visible_windows())
    env = os.environ.copy()
    env.update({
        "GROKBOT_VOICE_SAYTEST": "1",
        "APPDATA": appdata,
        "LOCALAPPDATA": local,
        "TEMP": temp,
        "TMP": temp,
    })
    env.pop("GROKBOT_VOICE_SELFTEST", None)
    env.pop("GROKBOT_VOICE_WATCHTEST", None)
    proc = subprocess.Popen([args.exe], env=env, cwd=os.path.dirname(args.exe))
    seen = {}
    deadline = time.time() + 90
    while proc.poll() is None and time.time() < deadline:
        for hwnd in visible_windows():
            if hwnd in before or hwnd in seen:
                continue
            kind, image, pid = window_owner(hwnd)
            own = image.lower()
            if own == "grokbot voice.exe":
                continue
            # The toolbar is the app. Anything else that appears while Piper
            # runs, including a conhost or piper.exe console, is a flash.
            seen[hwnd] = "%s %s pid %s" % (kind or "?", image or "?", pid)
        time.sleep(0.1)
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=15)
    log_path = os.path.join(temp, "grokbot_voice_log.txt")
    text = ""
    if os.path.isfile(log_path):
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    spoken = "piper says hello" in text and "(natural)" in text
    ran = os.path.isfile(os.path.join(piper, "piper-ran.txt"))
    wav = os.path.join(temp, "grok_voice_say.wav")
    heard = os.path.isfile(wav) and os.path.getsize(wav) > 44
    # A runner with no sound device still synthesizes. Only that playback error is allowed.
    problems = [line for line in text.splitlines() if "Voice problem" in line]
    play_ok = all("Failed to play sound" in line for line in problems)
    print("--- log ---")
    print(text)
    print("--- summary spoken %s ran %s wav %s play %s windows %s exit %s ---" % (
        "yes" if spoken else "no",
        "yes" if ran else "no",
        "yes" if heard else "no",
        "yes" if play_ok and not problems else ("no-device" if play_ok else "no"),
        ",".join(seen.values()) or "none",
        proc.returncode,
    ))
    if spoken and ran and heard and play_ok and not seen and proc.returncode == 0:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
