#!/usr/bin/env python3
"""Run-at-most-two-heavy-jobs-at-once guard, for anything that hammers CPU/GPU/RAM: video
encodes, the Apple Vision QA probe, headless-Chrome rendering. Two file locks cap system-wide
concurrency at 2 regardless of how many callers are running; a new job waits for >=35% free
memory before it starts, and is SIGTERM'd (then SIGKILL'd if it won't die) if free memory drops
below 12% while it runs. This matters most when several agents or terminal tabs build previews /
render storyboards / run QA at the same time on one machine.

  python3 scripts/with_heavy_lock.py -- ffmpeg -i in.mp4 ... out.mp4
  python3 scripts/with_heavy_lock.py -- python3 -m qa.pixel_qa video.mp4 --out-dir out/

Lock directory defaults to <repo>/.cache/locks (already gitignored via .cache/); override with
XM_LOCK_DIR if you want a wider or narrower scope than "this checkout" (e.g. one lock dir shared
by several checkouts on the same machine). XM_LOCK_MIN_FREE_START / XM_LOCK_MIN_FREE_KILL override
the 35% / 12% thresholds. On a non-macOS box (no `memory_pressure`), the memory checks are skipped
rather than failing — jobs still queue behind the concurrency cap.
"""
import fcntl
import os
import re
import signal
import subprocess
import sys
import time

LOCK_DIR = os.environ.get("XM_LOCK_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "locks"
)
LOCKS = [os.path.join(LOCK_DIR, ".heavy.lock"), os.path.join(LOCK_DIR, ".heavy2.lock")]
MIN_FREE_TO_START = int(os.environ.get("XM_LOCK_MIN_FREE_START", "35"))
MIN_FREE_TO_SURVIVE = int(os.environ.get("XM_LOCK_MIN_FREE_KILL", "12"))


def free_pct():
    try:
        out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=30).stdout
        m = re.search(r"free percentage:\s*(\d+)%", out)
        return int(m.group(1)) if m else 100
    except Exception:
        return 100  # no memory_pressure on this platform: don't block on it


def acquire():
    os.makedirs(LOCK_DIR, exist_ok=True)
    while True:
        for path in LOCKS:
            h = open(path, "a")
            try:
                fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return h
            except BlockingIOError:
                h.close()
        time.sleep(2)


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        sys.exit("usage: with_heavy_lock.py [--] CMD [ARGS...]")
    t0 = time.time()
    lock = acquire()
    while free_pct() < MIN_FREE_TO_START:
        time.sleep(10)
    print(f'[heavy-lock] {os.path.basename(lock.name)} acquired after {time.time() - t0:.0f}s: {" ".join(argv)[:120]}',
          file=sys.stderr, flush=True)
    p = subprocess.Popen(argv, start_new_session=True)

    def stop(signum, frame):
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except Exception:
            pass
        sys.exit(128 + signum)

    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, stop)
    while p.poll() is None:
        time.sleep(5)
        if free_pct() < MIN_FREE_TO_SURVIVE:
            os.killpg(p.pid, signal.SIGTERM)
            time.sleep(5)
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
            print(f"[heavy-lock] killed: system memory free < {MIN_FREE_TO_SURVIVE}%", file=sys.stderr, flush=True)
            sys.exit(99)
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
