# Run the frozen Windows app while a long-named chat blob is replaced underneath it.
# Grok Bot writes a temp file, deletes the old blob, and renames the temp into place.
# The blob's full path is at least 264 characters, past MAX_PATH, and the app has
# to open it with the \\?\ prefix. LongPathsEnabled is set to 0 for this process
# when the runner allows it, then put back. The app itself never changes that key.
import argparse
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import grok_store


FILESYSTEM_KEY = r"SYSTEM\CurrentControlSet\Control\FileSystem"


def blob_path(store, key):
    return os.path.join(store, grok_store.encode_base32(key) + ".blob")


def atomic_replace(path, payload):
    tmp = path + ".tmp"
    with open(grok_store.extended_path(tmp), "w", encoding="utf-8") as handle:
        handle.write(payload)
    if os.path.exists(grok_store.extended_path(path)):
        os.remove(grok_store.extended_path(path))
        time.sleep(0.05)
    os.replace(grok_store.extended_path(tmp), grok_store.extended_path(path))


def transcript(replies):
    entries = []
    for index, (msg_id, text) in enumerate(replies, start=1):
        entries.append(
            '{"kind":"send-message","id":"%s","seq":%d,"timestampMs":%d,"message":{"type":"text","content":"%s"}}'
            % (msg_id, index, 1700000000000 + index * 1000, text)
        )
    return '{"schemaVersion":1,"value":{"entries":[%s]}}' % ",".join(entries)


def registry_long_paths():
    """Current LongPathsEnabled, or None when it cannot be read."""
    if os.name != "nt":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, FILESYSTEM_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, "LongPathsEnabled")
        return int(value)
    except OSError:
        return None


def write_long_paths(value):
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, FILESYSTEM_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "LongPathsEnabled", 0, winreg.REG_DWORD, int(value))


def account_id(store, minimum=264):
    """Account id that makes the transcript blob's full path at least `minimum` characters."""
    chosen = None
    low, high = 1, 220
    while low <= high:
        mid = (low + high) // 2
        account = "a" * mid
        key = "sand.client.slice.account.%s.transcript.replicas.moya" % account
        filename = grok_store.encode_base32(key) + ".blob"
        if len(filename) > 255:
            high = mid - 1
            continue
        length = len(os.path.abspath(os.path.join(store, filename)))
        if length >= minimum:
            chosen = account
            high = mid - 1
        else:
            low = mid + 1
    if not chosen:
        raise SystemExit("could not make a blob path of %d characters in %s" % (minimum, store))
    return chosen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--workdir", required=True)
    args = parser.parse_args()
    original = registry_long_paths()
    changed = False
    code = 1
    try:
        if original not in (None, 0):
            try:
                write_long_paths(0)
                changed = True
            except OSError as exc:
                print("could not set LongPathsEnabled=0: %s" % exc)
        active = registry_long_paths()
        appdata = os.path.join(args.workdir, "roaming")
        local = os.path.join(args.workdir, "local")
        temp = os.path.join(args.workdir, "temp")
        store = os.path.join(appdata, "Grok Bot", "sand-client-persistence")
        os.makedirs(grok_store.extended_path(store), exist_ok=True)
        os.makedirs(grok_store.extended_path(local), exist_ok=True)
        os.makedirs(grok_store.extended_path(temp), exist_ok=True)
        account = account_id(store)
        roster_key = "sand.client.slice.account.%s.roster.last-roster" % account
        transcript_key = "sand.client.slice.account.%s.transcript.replicas.moya" % account
        path = blob_path(store, transcript_key)
        length = len(os.path.abspath(path))
        if length < 264:
            raise SystemExit("blob path is %d characters, wanted at least 264" % length)
        roster = '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"}]}}'
        atomic_replace(blob_path(store, roster_key), roster)
        replies = [("old", "old reply")]
        atomic_replace(path, transcript(replies))
        print("blob path length %d longpaths %s" % (length, "unreadable" if active is None else active), flush=True)
        env = os.environ.copy()
        env.update({
            "GROKBOT_VOICE_WATCHTEST": "1",
            "GROKBOT_VOICE_WATCH_SECONDS": str(args.seconds),
            "GROKBOT_VOICE_HEARTBEAT": "60",
            "APPDATA": appdata,
            "LOCALAPPDATA": local,
            "TEMP": temp,
            "TMP": temp,
        })
        proc = subprocess.Popen([args.exe], env=env, cwd=os.path.dirname(args.exe))
        deadline = time.time() + args.seconds - 15
        next_reply = time.time() + 20
        number = 0
        while time.time() < deadline:
            if time.time() >= next_reply:
                number += 1
                replies.append(("n%d" % number, "reply %d" % number))
                # Partial write, then the real atomic replace, the way a save races a reader.
                partial = path + ".partial"
                with open(grok_store.extended_path(partial), "w", encoding="utf-8") as handle:
                    handle.write(transcript(replies)[:40])
                os.replace(grok_store.extended_path(partial), grok_store.extended_path(path))
                time.sleep(0.1)
                atomic_replace(path, transcript(replies))
                next_reply = time.time() + 30
            time.sleep(1)
        try:
            proc.wait(timeout=args.seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=30)
        log_path = os.path.join(temp, "grokbot_voice_log.txt")
        text = ""
        if os.path.isfile(grok_store.extended_path(log_path)):
            with open(grok_store.extended_path(log_path), encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        missing = ["reply %d" % n for n in range(1, number + 1)
                   if not re.search(r"speak .*reply %d\b" % n, text)]
        hearts = text.count("watching: ")
        print("--- log ---")
        print(text)
        print("--- summary replies %d heartbeats %d missing %s path %d longpaths %s exit %s ---" % (
            number, hearts, ",".join(missing) or "none", length,
            "unreadable" if active is None else active, proc.returncode))
        if not missing and hearts >= 8 and proc.returncode == 0:
            code = 0
    finally:
        if changed and original is not None:
            try:
                write_long_paths(original)
            except OSError as exc:
                print("could not restore LongPathsEnabled: %s" % exc)
                code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
