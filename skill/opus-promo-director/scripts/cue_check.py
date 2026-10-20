"""Check that the sound effects in a finished video land on their cue frames.

Usage: python cue_check.py VIDEO production/shotlist.json [--window-ms 80] [--project film/]
For each cue, compares loudness just before the cue with the loudest moment in a short window after it.
A cue passes when loudness rises by at least --min-rise dB. Cues buried under loud music report as weak;
listen to those spots before calling them misaligned.
"""
import argparse, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _media import decode_audio, set_project  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("shotlist")
    ap.add_argument("--window-ms", type=float, default=80)
    ap.add_argument("--min-rise", type=float, default=1.5)
    ap.add_argument("--project", default=None)
    a = ap.parse_args()
    set_project(a.project)
    shot = json.load(open(a.shotlist, encoding="utf-8-sig"))
    fps = shot["fps"]
    sr = 44100
    x = decode_audio(a.video, sr, 1)[:, 0]
    if not len(x):
        sys.exit("no audio")
    hop = 220
    n = len(x) // hop
    db = 20 * np.log10(np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-6)
    step = hop / sr
    ok, weak = 0, []
    cues = shot.get("cues", [])
    for c in cues:
        i = int(c["frame"] / fps / step)
        pre = db[max(0, i - int(0.12 / step)):max(1, i - int(0.05 / step))]
        post = db[max(0, i - int(0.05 / step)):i + int(a.window_ms / 1000 / step)]
        if not len(pre) or not len(post):
            weak.append((c.get("id", c["frame"]), None))
            continue
        rise = float(post.max() - pre.mean())
        if rise >= a.min_rise:
            ok += 1
        else:
            weak.append((c.get("id", c["frame"]), round(rise, 1)))
    print(f"{ok}/{len(cues)} cues show a loudness rise of {a.min_rise} dB or more")
    for cid, rise in weak:
        print(f"  weak: {cid} (rise {rise} dB) - listen here")
    sys.exit(0)


if __name__ == "__main__":
    main()

