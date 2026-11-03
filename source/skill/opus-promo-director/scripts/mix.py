"""Build the soundtrack from a shot list: cut the song on bar lines, place sound effects on cue frames.

Usage:
  python mix.py production/shotlist.json OUT.wav [--sfx-dir sfx/] [--project film/]
Then master for AAC:  python master_wav.py OUT.wav film/public/audio/mix.wav --ceiling -4

Shot list fields used (all optional except fps and totalFrames):
  "fps": 30, "totalFrames": 1800,
  "music": {"src": "music/song.mp3", "edit": [[7.89, 23.89], [43.89, 55.89], [75.89, null]],
            "gain_db": -2.5, "fade_out": 1.2, "crossfade_ms": 30},
  "cues": [{"id": "ev1_hit", "frame": 182, "sfx": [["whoosh", -10, "peak", 0.0]]}]
Each sfx entry is [name, gain_db, align, pan]. name is a file in --sfx-dir without extension, or one of
the built-ins "thump" (low hit) and "tick" (short high click). align "onset" puts the start of the sound
on the frame, "peak" puts its loudest moment there. pan runs from -1 (left) to 1 (right).
Edit segments are [start_sec, end_sec] of the song, played back to back; null means to the end. Pick
cut points on bar lines of the song so the join is inaudible.
"""
import argparse, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _media import decode_audio, set_project, write_wav  # noqa: E402

SR = 44100


def builtin(name):
    t = np.arange(int(0.35 * SR)) / SR
    if name == "thump":
        ph = 2 * np.pi * np.cumsum(48 + 80 * np.exp(-t / 0.035)) / SR
        s = np.sin(ph) * np.exp(-t / 0.11) + np.random.default_rng(2).normal(0, 1, len(t)) * np.exp(-t / 0.004) * 0.25
    elif name == "tick":
        t = t[: int(0.08 * SR)]
        s = np.sin(2 * np.pi * 1800 * t) * np.exp(-t / 0.012)
    else:
        return None
    s = s / np.abs(s).max() * 0.9
    return np.stack([s, s], 1)


def load_sfx(name, sfx_dir, cache):
    if name in cache:
        return cache[name]
    x = builtin(name)
    if x is None:
        for ext in (".wav", ".mp3", ".ogg", ".flac", ".m4a"):
            p = os.path.join(sfx_dir or "", name + ext)
            if os.path.exists(p):
                x = decode_audio(p, SR, 2)
                break
    if x is None or not len(x):
        sys.exit(f"sound effect '{name}' not found in {sfx_dir}")
    mono = np.abs(x).max(1)
    hop = int(0.005 * SR)
    n = len(mono) // hop
    env = np.sqrt((x[: n * hop].mean(1).reshape(n, hop) ** 2).mean(1)) if n else np.zeros(1)
    meta = {"onset": float(np.argmax(mono > mono.max() * 0.1)) / SR, "peak": float(np.argmax(env)) * 0.005}
    cache[name] = (x, meta)
    return cache[name]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shotlist")
    ap.add_argument("out")
    ap.add_argument("--sfx-dir", default=None)
    ap.add_argument("--project", default=None, help="Remotion project, used to find its bundled ffmpeg")
    a = ap.parse_args()
    set_project(a.project)
    base = os.path.dirname(os.path.abspath(a.shotlist))
    shot = json.load(open(a.shotlist, encoding="utf-8-sig"))
    fps = shot["fps"]
    total = int(round(shot["totalFrames"] / fps * SR))
    out = np.zeros((total, 2))

    m = shot.get("music")
    if m:
        src = m["src"] if os.path.isabs(m["src"]) or os.path.exists(m["src"]) else os.path.join(base, m["src"])
        song = decode_audio(src, SR, 2)
        edit = m.get("edit") or [[0, None]]
        xf = int(m.get("crossfade_ms", 30) / 1000 * SR)
        pos = 0
        for i, (s0, s1) in enumerate(edit):
            a0 = int(round(s0 * SR))
            a1 = len(song) if s1 is None else int(round(s1 * SR))
            seg = song[a0:a1].copy()
            if i == 0 and a0 > 0:
                k = min(len(seg), int(0.01 * SR))
                seg[:k] *= np.linspace(0, 1, k)[:, None]
            if i > 0 and xf and pos >= xf and a0 >= xf:
                t = np.linspace(0, 1, xf)[:, None]
                out[pos - xf:pos] *= np.cos(t * np.pi / 2)
                out[pos - xf:pos] += song[a0 - xf:a0] * np.sin(t * np.pi / 2)
            n = max(0, min(len(seg), total - pos))
            out[pos:pos + n] += seg[:n]
            pos += len(seg)
            print(f"segment {s0}-{s1 if s1 is not None else 'end'}s ends at {pos / SR:.3f}s of the edit")
        if pos < total:
            print(f"note: music ends {(total - pos) / SR:.2f}s before the video ends", file=sys.stderr)
        fo = int(m.get("fade_out", 1.0) * SR)
        if fo:
            out[total - fo:] *= np.linspace(1, 0, fo)[:, None]
        pk = np.abs(out).max()
        if pk > 0:
            out *= 10 ** (m.get("gain_db", -2.5) / 20) / pk

    cache, placed = {}, 0
    sfx_dir = a.sfx_dir or os.path.join(base, "sfx")
    for c in shot.get("cues", []):
        for name, gain, align, pan in c.get("sfx", []):
            x, meta = load_sfx(name, sfx_dir, cache)
            st = int(round((c["frame"] / fps - meta.get(align, 0.0)) * SR))
            g = 10 ** (gain / 20)
            ang = (pan + 1) * np.pi / 4
            gl, gr = np.cos(ang) * np.sqrt(2), np.sin(ang) * np.sqrt(2)
            s0, s1 = max(0, st), min(total, st + len(x))
            if s1 <= s0:
                continue
            xs = x[s0 - st:s1 - st]
            out[s0:s1, 0] += xs[:, 0] * g * gl
            out[s0:s1, 1] += xs[:, 1] * g * gr
            placed += 1
    pk = np.abs(out).max()
    print(f"placed {placed} sound effects, pre-master peak {20 * np.log10(max(pk, 1e-9)):.2f} dBFS")
    if pk > 0.98:
        out *= 0.98 / pk
    write_wav(a.out, out, SR)
    print(f"wrote {a.out} ({total / SR:.2f}s). Next: master_wav.py {a.out} <public/audio/...> --ceiling -4")


if __name__ == "__main__":
    main()

