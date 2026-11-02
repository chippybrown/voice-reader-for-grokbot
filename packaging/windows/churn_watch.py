# Run the frozen Windows app while chat blobs are replaced underneath it.
# Grok Bot writes a temp file, deletes the old blob, and renames the temp into place.
import argparse
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import grok_store


ROSTER = "sand.client.slice.account.a.roster.last-roster"
TRANSCRIPT = "sand.client.slice.account.a.transcript.replicas.moya"


def blob_path(store, key):
    return os.path.join(store, grok_store.encode_base32(key) + ".blob")


def atomic_replace(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(payload)
    if os.path.exists(path):
        os.remove(path)
        time.sleep(0.05)
    os.replace(tmp, path)


def transcript(replies):
    entries = []
    for index, (msg_id, text) in enumerate(replies, start=1):
        entries.append(
            '{"kind":"send-message","id":"%s","seq":%d,"timestampMs":%d,"message":{"type":"text","content":"%s"}}'
            % (msg_id, index, 1700000000000 + index * 1000, text)
        )
    return '{"schemaVersion":1,"value":{"entries":[%s]}}' % ",".join(entries)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--workdir", required=True)
    args = parser.parse_args()
    appdata = os.path.join(args.workdir, "roaming")
    local = os.path.join(args.workdir, "local")
    temp = os.path.join(args.workdir, "temp")
    store = os.path.join(appdata, "Grok Bot", "sand-client-persistence")
    os.makedirs(store, exist_ok=True)
    os.makedirs(local, exist_ok=True)
    os.makedirs(temp, exist_ok=True)
    roster = '{"schemaVersion":1,"value":{"rows":[{"id":"moya","name":"Moya"}]}}'
    atomic_replace(blob_path(store, ROSTER), roster)
    path = blob_path(store, TRANSCRIPT)
    replies = [("old", "old reply")]
    atomic_replace(path, transcript(replies))
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
            with open(partial, "w", encoding="utf-8") as handle:
                handle.write(transcript(replies)[:40])
            os.replace(partial, path)
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
    if os.path.isfile(log_path):
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    missing = ["reply %d" % n for n in range(1, number + 1) if not re.search(r"reply %d\b" % n, text)]
    hearts = text.count("watching: ")
    print("--- log ---")
    print(text)
    print("--- summary replies %d heartbeats %d missing %s exit %s ---" % (
        number, hearts, ",".join(missing) or "none", proc.returncode))
    if missing or hearts < 8:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
