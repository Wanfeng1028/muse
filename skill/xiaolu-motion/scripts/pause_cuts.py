#!/usr/bin/env python3
"""Cut list for tightening pauses ("气口") between phrases, plus a command that applies it.

Generalized from a real project's pause-cutting pass (see `library/_shared/video20-a0-pipeline/`
for that project-specific version, which additionally protects a shot table's own animation
windows). This standalone tool only needs a word-level transcript — `timeline/words.py`'s
`words.json` format (`{"words": [{"w", "s", "e"}, ...]}`) — and, optionally, a list of extra
protected time spans (SFX cues, on-screen animations, anything a storyboard already knows must
stay intact) you don't want a cut to land inside.

  python3 scripts/pause_cuts.py detect --words words.json --audio voice.wav -o cuts.json
  python3 scripts/pause_cuts.py detect --words words.json --video clip.mp4 --protect protect.json -o cuts.json
  python3 scripts/pause_cuts.py apply cuts.json --video clip.mp4 -o clip.cut.mp4
  python3 scripts/pause_cuts.py apply cuts.json --audio voice.wav -o voice.cut.wav

Rules (defaults match the project this was generalized from):
  * a pause = the gap between two consecutive words' [s, e] longer than --min-gap (default 0.25s).
  * it is shortened to ~--mid-keep (0.15s) inside a sentence, ~--end-keep (0.22s) after a sentence
    end; the previous word's text must end with one of --sentence-end-chars (default `。？！.!?`)
    for the longer, "sentence end" keep to apply — if your transcript doesn't carry punctuation on
    words, every gap is treated as mid-sentence (safe default, just not sentence-aware).
  * at least --tail (0.07s) is kept after the previous word and --head (0.08s) before the next one;
    the rest of the target keep-time is split evenly between the two sides.
  * a --protect span inside the candidate cut shrinks it to the largest remaining free sub-interval
    (less is cut; the pause is never skipped outright) unless nothing is left, in which case the
    pause is left alone and recorded under "skipped" in the output.
  * only silence is cut: the candidate span (widened by half a crossfade on each side) is checked
    against the loaded audio and shrunk frame-by-frame from whichever side is louder until its peak
    is below --silence-db (default -66 dBFS). A cut that can't get short enough is dropped.
  * with --fps, cut boundaries snap inward to frame boundaries (so video and audio cut at exactly
    the same sample-accurate points); without it, boundaries stay at raw sample precision.

`apply` cuts video with hard concat at the shared boundaries (no video crossfade — a hard cut is
standard for silence removal; crossfading video frames would visibly ghost) and audio with an
equal-power crossfade (default 12ms, --crossfade-ms, kept inside the 10-15ms range this was
designed around) at every join, so the edit doesn't click. Video and audio always share the exact
same cut points, so lip-sync is preserved.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

SENTENCE_END_CHARS = "。？！.!?"


# ---------------------------------------------------------------------------
# audio in/out via ffmpeg (no project-specific dependency: works on any file
# ffmpeg can decode)
# ---------------------------------------------------------------------------

def ffprobe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                        check=True, capture_output=True, text=True)
    return float(r.stdout.strip())


def ffprobe_fps(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=r_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                        check=True, capture_output=True, text=True)
    s = r.stdout.strip()
    if not s:
        return None
    num, _, den = s.partition("/")
    return float(num) / float(den or 1)


def has_video_stream(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=index",
                         "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return bool(r.stdout.strip())


def decode_mono(path, sr=44100):
    """any ffmpeg-readable media -> mono float32 PCM at sr Hz (for the silence check only)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(sr),
                         "-f", "f32le", "-"], check=True, capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32), sr


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

def load_words(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    words = d["words"] if isinstance(d, dict) else d
    return sorted(({"w": w.get("w", ""), "s": float(w["s"]), "e": float(w["e"])} for w in words), key=lambda w: w["s"])


def load_protect(path):
    if not path:
        return []
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return [(float(p["start"]), float(p["end"]), p.get("why", "protected")) for p in d]


def subtract(a, b, spans):
    """free parts of [a, b) after removing spans -> ([(x0,x1), ...], [why, ...] of spans that overlapped)"""
    free, hit = [(a, b)], []
    for s0, s1, why in spans:
        if s1 <= a or s0 >= b:
            continue
        hit.append(why)
        nxt = []
        for x0, x1 in free:
            if s1 <= x0 or s0 >= x1:
                nxt.append((x0, x1))
                continue
            if s0 > x0:
                nxt.append((x0, s0))
            if s1 < x1:
                nxt.append((s1, x1))
        free = nxt
    return free, hit


def peak_db(x, sr, t0, t1, pad_s):
    a, b = int((t0 - pad_s) * sr), int((t1 + pad_s) * sr)
    a, b = max(0, a), min(len(x), b)
    if b <= a:
        return -120.0
    win = max(1, sr // 100)  # ~10ms windows, like the source implementation's 441 @ 44.1kHz
    n = (b - a) // win
    if n == 0:
        seg = x[a:b]
        return float(20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-12)) if len(seg) else -120.0
    seg = x[a:a + n * win].reshape(n, win)
    return float(20 * np.log10(np.sqrt((seg ** 2).mean(1)).max() + 1e-12))


def detect(a):
    words = load_words(a.words)
    if len(words) < 2:
        sys.exit("need at least 2 words to find a gap between them")
    protect = load_protect(a.protect)
    fps = a.fps
    if fps is None and a.video and has_video_stream(a.video):
        fps = ffprobe_fps(a.video)

    audio_src = a.audio or a.video
    if not audio_src:
        sys.exit("detect needs --audio or --video (to verify a candidate cut is actually silent)")
    x, sr = decode_mono(audio_src)
    xfade_pad = (a.crossfade_ms / 2000.0) + 0.0075  # half the crossfade + the same small margin the source used

    cuts, skipped = [], []
    for i in range(len(words) - 1):
        e0, s1 = words[i]["e"], words[i + 1]["s"]
        gap = s1 - e0
        if gap <= a.min_gap:
            continue
        sentence_end = words[i]["w"].rstrip().endswith(tuple(a.sentence_end_chars))
        keep = a.end_keep if sentence_end else a.mid_keep
        extra = (keep - (a.tail + a.head)) / 2
        c0, c1 = e0 + a.tail + extra, s1 - a.head - extra
        if c1 <= c0:
            continue
        free, hit = subtract(c0, c1, protect)
        if not free:
            skipped.append({"reason": "fully protected", "gap_s": round(gap, 3), "at": round(e0, 3), "protected_by": hit})
            continue
        f0, f1 = max(free, key=lambda p: p[1] - p[0])
        if fps:
            f0, f1 = math.ceil(f0 * fps - 1e-6) / fps, math.floor(f1 * fps + 1e-6) / fps
        if f1 - f0 <= 0:
            skipped.append({"reason": "nothing left after protection/frame snap", "gap_s": round(gap, 3), "at": round(e0, 3), "protected_by": hit})
            continue
        # shrink from whichever side is louder until the (padded) span is below the silence threshold
        while f1 - f0 > (1 / fps if fps else 0.001) and peak_db(x, sr, f0, f1, xfade_pad) >= a.silence_db:
            step = 1 / fps if fps else 0.005
            if peak_db(x, sr, f0, f0 + step, xfade_pad) >= peak_db(x, sr, f1 - step, f1, xfade_pad):
                f0 += step
            else:
                f1 -= step
        if f1 - f0 <= 0:
            skipped.append({"reason": "no silent sub-span found (touches speech)", "gap_s": round(gap, 3), "at": round(e0, 3)})
            continue
        cuts.append({
            "start": round(f0, 4), "end": round(f1, 4), "removed_s": round(f1 - f0, 4),
            "kind": "sentence_end" if sentence_end else "mid", "gap_orig_s": round(gap, 4),
            "prev_word": words[i]["w"], "next_word": words[i + 1]["w"],
            "max_voice_db": round(peak_db(x, sr, f0, f1, xfade_pad), 1),
            "reduced_by": hit,
        })
    total_removed = sum(c["removed_s"] for c in cuts)
    out = {
        "version": "0.1", "tool": "pause_cuts.py", "min_gap_s": a.min_gap, "mid_keep_s": a.mid_keep,
        "end_keep_s": a.end_keep, "silence_db": a.silence_db, "fps": fps, "crossfade_ms": a.crossfade_ms,
        "n_cuts": len(cuts), "removed_s": round(total_removed, 3), "cuts": cuts, "skipped": skipped,
    }
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"n_cuts": len(cuts), "removed_s": round(total_removed, 3), "skipped": len(skipped)}, ensure_ascii=False))
    if a.video or a.audio:
        tgt = a.video or a.audio
        suffix = Path(tgt).suffix
        print(f"# apply with:\npython3 {Path(__file__).name} apply {a.out} "
              f"{'--video' if a.video else '--audio'} {tgt} -o {Path(tgt).stem}.cut{suffix}")


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def kept_segments(cuts, total_dur):
    spans = sorted((c["start"], c["end"]) for c in cuts)
    pieces, pos = [], 0.0
    for a0, b0 in spans:
        if a0 > pos:
            pieces.append((pos, a0))
        pos = max(pos, b0)
    if pos < total_dur:
        pieces.append((pos, total_dur))
    return [(a0, b0) for a0, b0 in pieces if b0 > a0]


def build_filter(segments, has_v, has_a, xf_s):
    parts, vlabels, alabels = [], [], []
    for i, (a0, b0) in enumerate(segments):
        if has_v:
            parts.append(f"[0:v]trim=start={a0:.6f}:end={b0:.6f},setpts=PTS-STARTPTS[v{i}]")
            vlabels.append(f"[v{i}]")
        if has_a:
            parts.append(f"[0:a]atrim=start={a0:.6f}:end={b0:.6f},asetpts=PTS-STARTPTS[a{i}]")
            alabels.append(f"[a{i}]")
    if has_v:
        parts.append("".join(vlabels) + f"concat=n={len(vlabels)}:v=1:a=0[vout]")
    if has_a:
        if len(alabels) == 1:
            parts.append(f"{alabels[0]}anull[aout]")
        else:
            # chain acrossfade pairwise so every join gets a short equal-power crossfade
            cur = alabels[0]
            for i in range(1, len(alabels)):
                nxt_label = f"[axf{i}]" if i < len(alabels) - 1 else "[aout]"
                dur = min(xf_s, max(0.001, segments[i][1] - segments[i][0]) * 0.4,
                          max(0.001, segments[i - 1][1] - segments[i - 1][0]) * 0.4)
                parts.append(f"{cur}{alabels[i]}acrossfade=d={dur:.4f}:c1=tri:c2=tri{nxt_label}")
                cur = nxt_label
    return ";".join(parts)


def apply(a):
    cuts = json.loads(Path(a.cuts).read_text(encoding="utf-8"))["cuts"]
    if not cuts:
        sys.exit("no cuts in the cut list — nothing to do")
    src = a.video or a.audio
    if not src:
        sys.exit("apply needs --video or --audio")
    dur = ffprobe_duration(src)
    segs = kept_segments(cuts, dur)
    has_v = bool(a.video) and has_video_stream(a.video)
    has_a = True  # every input here has at least an audio track to cut; video-only silent input is not the target use case
    filt = build_filter(segs, has_v, has_a, a.crossfade_ms / 1000.0)
    maps = (["-map", "[vout]"] if has_v else []) + ["-map", "[aout]"]
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src, "-filter_complex", filt] + maps
    if has_v:
        cmd += ["-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "pcm_s16le" if Path(a.out).suffix.lower() == ".wav" else "aac"]
    part = Path(str(a.out) + ".partial" + Path(a.out).suffix)
    subprocess.run(cmd + [str(part)], check=True)
    part.replace(a.out)  # atomic rename: never leave a half-written file at the final name
    # each audio join is an acrossfade, which blends (and so shortens) the output by its own
    # duration -- report the duration that's actually on disk, not the naive sum of segment lengths
    xf_total = sum(min(a.crossfade_ms / 1000.0, max(0.001, segs[i][1] - segs[i][0]) * 0.4,
                        max(0.001, segs[i - 1][1] - segs[i - 1][0]) * 0.4) for i in range(1, len(segs)))
    kept_dur = sum(b - a0 for a0, b in segs) - xf_total
    print(json.dumps({"segments": len(segs), "cuts_applied": len(cuts), "kept_duration_s": round(kept_dur, 3),
                       "original_duration_s": round(dur, 3), "out": str(a.out)}, ensure_ascii=False))


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    d = sp.add_parser("detect", help="find pause cuts from a word-level transcript")
    d.add_argument("--words", required=True, help="words.json ({'words':[{'w','s','e'}, ...]}, see timeline/words.py)")
    d.add_argument("--audio", help="voice audio file (for the silence check); required if --video is not given")
    d.add_argument("--video", help="video file (audio track is used for the silence check; enables --fps auto-detect)")
    d.add_argument("--protect", help="JSON list of [{'start','end','why'?}] spans that must not be cut into")
    d.add_argument("--min-gap", type=float, default=0.25, dest="min_gap")
    d.add_argument("--mid-keep", type=float, default=0.15, dest="mid_keep")
    d.add_argument("--end-keep", type=float, default=0.22, dest="end_keep")
    d.add_argument("--tail", type=float, default=0.07)
    d.add_argument("--head", type=float, default=0.08)
    d.add_argument("--silence-db", type=float, default=-66.0, dest="silence_db")
    d.add_argument("--sentence-end-chars", default=SENTENCE_END_CHARS, dest="sentence_end_chars")
    d.add_argument("--fps", type=float, help="snap cut boundaries to frame boundaries (auto-detected from --video if omitted)")
    d.add_argument("--crossfade-ms", type=float, default=12.0, dest="crossfade_ms", help="only affects the silence-check padding here; also the default for `apply`")
    d.add_argument("-o", "--out", required=True)
    d.set_defaults(fn=detect)

    p = sp.add_parser("apply", help="cut a video/audio file at a cut list's boundaries")
    p.add_argument("cuts", help="cut list JSON produced by `detect`")
    p.add_argument("--video")
    p.add_argument("--audio")
    p.add_argument("--crossfade-ms", type=float, default=12.0, dest="crossfade_ms")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(fn=apply)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
