"""Map a song for editing: tempo, first beat, bar grid and loudness per bar.

Usage: python song_map.py SONG.mp3 [--fps 30] [--beats-per-bar 4] [--bpm-min 70] [--bpm-max 180] [--project film/]
Prints the tempo, where the first beat falls and frames per beat at --fps, then one line per bar with its start
time, start frame and loudness. Bars where the level jumps (quiet -> loud and back) are marked as section starts.
Cut the song on those bar starts so the join is inaudible, and put the hero reveal on the loudest section start.
The downbeat guess can be one beat off, and swing, tempo changes or songs without clear drums can give half or
double tempo. Listen at the first section start before building the edit on it.
"""
import argparse, math, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _media import decode_audio, set_project  # noqa: E402

SR, HOP, N = 22050, 256, 1024
RATE = SR / HOP
# flux[i] compares STFT frames i and i+1; its onset sits between their window centres
OFFSET = (0.5 * HOP + N / 2) / SR


def onset_envelopes(x):
    frames = np.lib.stride_tricks.sliding_window_view(x, N)[::HOP] * np.hanning(N)
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)))
    freqs = np.fft.rfftfreq(N, 1 / SR)
    flux = np.maximum(0, np.diff(mag, axis=0))

    def z(v):
        return (v - v.mean()) / (v.std() + 1e-9)
    return z(flux.sum(1)), z(flux[:, freqs < 150].sum(1))


def grid(env, bpm, phases):
    per = RATE * 60 / bpm
    best = (-1e9, 0.0)
    for ph in np.linspace(0, per, phases, endpoint=False):
        idx = np.round(np.arange(ph, len(env) - 1, per)).astype(int)
        s = float(env[idx].mean())
        if s > best[0]:
            best = (s, ph)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("song")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--beats-per-bar", type=int, default=4)
    ap.add_argument("--bpm-min", type=float, default=70)
    ap.add_argument("--bpm-max", type=float, default=180)
    ap.add_argument("--jump-db", type=float, default=2.5, help="level change that starts a new section")
    ap.add_argument("--project", default=None)
    a = ap.parse_args()
    set_project(a.project)

    x = decode_audio(a.song, SR, 1)[:, 0]
    if len(x) < SR * 4:
        sys.exit("song is shorter than 4 seconds")
    full, low = onset_envelopes(x)

    # coarse search with a mild pull toward 120 BPM to avoid half/double tempo, then refine
    def score(b):
        s, _ = grid(full, b, 32)
        return s - 0.15 * abs(math.log2(b / 120))
    coarse = sorted(((score(b), b) for b in np.arange(a.bpm_min, a.bpm_max + 1e-9, 0.5)), reverse=True)
    top = coarse[0][1]
    fine = [(grid(full, b, 96)[0], b) for b in np.arange(top - 0.6, top + 0.6 + 1e-9, 0.02)]
    bpm = max(fine)[1]
    if abs(bpm - round(bpm)) < 0.06:
        bpm = float(round(bpm))
    _, ph = grid(full, bpm, 192)
    beat = 60 / bpm
    first = ph / RATE + OFFSET
    while first - beat >= 0:
        first -= beat

    # downbeat: the beat position in the bar with the strongest onsets, weighted toward low frequencies
    both = full + low
    per = RATE * 60 / bpm
    idx = np.round(np.arange(ph, len(both) - 1, per)).astype(int)
    k = a.beats_per_bar
    strength = [float(both[idx[o::k]].mean()) if len(idx[o::k]) else -1e9 for o in range(k)]
    # idx[0] is the beat at ph, which is 'first' plus some whole beats
    shift = int(round((ph / RATE + OFFSET - first) / beat))
    o = int(np.argmax(strength))
    bar0 = first + ((o + shift) % k) * beat
    bar = beat * k

    fpb = a.fps * beat
    whole = abs(fpb - round(fpb)) < 1e-6
    print(f"tempo {bpm:.2f} BPM (beat {beat:.3f}s), first beat {first:.3f}s, "
          f"{fpb:.3f} frames per beat at {a.fps:g}fps ({'whole' if whole else 'not whole: round each cut'})")
    print(f"downbeat guess: bars start at {bar0:.3f}s + n x {bar:.3f}s ({k} beats per bar). "
          f"Also consider {bpm / 2:.1f} or {bpm * 2:.1f} BPM if the pulse feels half or double.")

    starts = np.arange(bar0, len(x) / SR - bar * 0.5, bar)
    levels = []
    for t in starts:
        s = x[int(t * SR):int((t + bar) * SR)]
        levels.append(20 * math.log10(math.sqrt(float((s ** 2).mean())) + 1e-9))
    levels = np.array(levels)
    sections = [0]
    for i in range(1, len(levels)):
        before = levels[max(0, i - 2):i].mean()
        after = levels[i:i + 2].mean()
        if abs(after - before) < a.jump_db:
            continue
        # the two-bar averages flag the bar just before a jump too; pick the bar with the biggest single step
        j = max((k for k in (i, i + 1) if k < len(levels)), key=lambda k: abs(levels[k] - levels[k - 1]))
        if j - sections[-1] >= 2:
            sections.append(j)
    print(f"{'bar':>4} {'start(s)':>9} {'frame':>6} {'level(dB)':>9}")
    for i, (t, lv) in enumerate(zip(starts, levels)):
        mark = ""
        if i in sections and i > 0:
            mark = f"  <- section start ({levels[i:i + 2].mean() - levels[max(0, i - 2):i].mean():+.1f} dB)"
        print(f"{i:4d} {t:9.3f} {round(t * a.fps):6d} {lv:9.1f}{mark}")
    cuts = [starts[i] for i in sections if i > 0]
    print("section starts (cut or reveal here): " + ", ".join(f"{t:.2f}" for t in cuts))
    if cuts:
        loud = max(sections[1:], key=lambda i: levels[i:i + 4].mean())
        print(f"loudest section starts at {starts[loud]:.2f}s (frame {round(starts[loud] * a.fps)})")
    end = len(x) / SR
    print(f"song length {end:.2f}s, {len(starts)} full bars from the first downbeat")


if __name__ == "__main__":
    main()
