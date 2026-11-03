# Ported from browser-use/video-use (MIT License, Copyright (c) 2026 Browser Use)
# https://github.com/browser-use/video-use at 9575612f066aa517354790a645fd90f9f95a743b
# Adapted from helpers/render.py (per-segment extract with 30 ms fades, portrait-aware
# scaling, one frame rate for every segment, lossless concat demuxer), the EDL format and
# the cut Hard Rules in its SKILL.md (never cut inside a word, pad 30 to 200 ms, output-timeline
# word offsets, self eval at every cut boundary). New for this rail: the edges are placed
# from Scribe word boundaries AND a 10 ms RMS envelope (the rail's audio-is-the-arbiter
# law), segment lengths are whole frames so audio and video cannot drift apart across
# cuts, and segments carry PCM audio so the only AAC encode is the final mux.
"""Rough cut for self-recorded takes: fillers, dead air, false starts and retakes out.

Subcommands (python3; verify needs Pillow):

  words   <edit-dir> <source> <start> <end>
          Word-level times for a stretch, to pick --drop ranges precisely.
  plan    --edit-dir D --source NAME=PATH [--source ...] [--drop NAME:START-END[:why]] ...
          Proposes edl.json from the cached Scribe transcripts: removes standalone fillers,
          non-laugh audio events, every --drop range (false starts, superseded retakes) and
          any gap >= --max-gap. Edges snap to word boundaries with padding. Nothing renders.
  render  --edit-dir D [--crf 16] [--fps R] [--height 1920]
          Per-segment extract (30 ms fades, whole-frame lengths) then concat -c copy, then
          one AAC mux: <D>/rough_cut.mp4, cut_words.json, cuts.json, render_report.json.
  verify  --edit-dir D
          timeline_view on the RENDERED cut at every boundary (+-1.5 s) plus head and tail,
          and numeric checks per boundary. Writes <D>/verify/. Exit 1 if anything flagged.

All times in edl.json are SOURCE seconds; cut_words.json and cuts.json are OUTPUT seconds.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import re
import statistics
import subprocess
import sys
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pack_transcripts import is_filler  # noqa: E402

PAD_IN, PAD_OUT = 0.05, 0.08      # upstream launch-video values, inside the 30-200 ms window
PAD_MIN, PAD_MAX = 0.03, 0.20     # Hard Rule: every edge padded 30 to 200 ms from its word
FADE = 0.03                       # Hard Rule: 30 ms audio fade at every segment edge
MAX_GAP = 0.40                    # silences at or above this are dead air (upstream: >=400 ms)
MIN_SEG = 0.60                    # a kept fragment shorter than this between cuts keeps one pause
HOP = 0.01                        # envelope hop, 10 ms
QUIET_RUN = 3                     # frames (30 ms) of quiet that count as a real pause


# ---------------------------------------------------------------- audio envelope

class Envelope:
    """20 ms RMS windows every 10 ms over a whole source, in dBFS, plus an adaptive
    quiet threshold: noise p10 + 30% of the way to speech p90 (measured on one phone take:
    noise -60.6, speech -22.7, threshold about -49 dBFS)."""

    def __init__(self, path: Path):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "a.wav"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-map", "0:a:0", "-vn",
                            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)
            with wave.open(str(wav), "rb") as w:
                pcm = array.array("h", w.readframes(w.getnframes()))
        self.db: list[float] = []
        for k in range(0, max(0, len(pcm) - 320) + 1, 160):
            seg = pcm[k:k + 320]
            r = math.sqrt(sum(s * s for s in seg) / max(1, len(seg))) / 32768.0
            self.db.append(20 * math.log10(r) if r > 0 else -120.0)
        s = sorted(self.db) or [-120.0]
        self.noise = s[int(0.10 * (len(s) - 1))]
        self.speech = s[int(0.90 * (len(s) - 1))]
        self.thr = self.noise + 0.30 * (self.speech - self.noise)

    def idx(self, t: float) -> int:
        return max(0, min(len(self.db) - 1, int(round(t / HOP))))

    def at(self, t: float) -> float:
        """Level of the 20 ms window STARTING at t (what a fade-in at t covers)."""
        return self.db[self.idx(t)]

    def before(self, t: float) -> float:
        """Level of the 20 ms window ENDING at t (what a fade-out ending at t covers)."""
        return self.db[self.idx(t - 0.02)]

    def quietest(self, lo: float, hi: float, key) -> float | None:
        """The 10 ms grid point in [lo, hi] where key() is lowest, or None if none fits."""
        pts = [i * HOP for i in range(self.idx(lo), self.idx(hi) + 2)]
        pts = [t for t in pts if lo - 1e-9 <= t <= hi + 1e-9]
        return min(pts, key=key) if pts else None

    def quiet(self, i: int) -> bool:
        return self.db[i] < self.thr

    def offset_after(self, t0: float, limit: float) -> float | None:
        """First time >= t0 where a quiet run of QUIET_RUN frames starts, before limit."""
        i, stop = self.idx(t0), self.idx(limit)
        while i <= stop:
            if all(self.quiet(j) for j in range(i, min(len(self.db), i + QUIET_RUN))):
                return i * HOP
            i += 1
        return None

    def onset_before(self, t0: float, limit: float) -> float | None:
        """Scanning back from t0: the end of the nearest quiet run (the speech onset)."""
        i, stop = self.idx(t0), self.idx(limit)
        while i >= stop:
            if all(self.quiet(j) for j in range(max(0, i - QUIET_RUN + 1), i + 1)):
                return (i + 1) * HOP
            i -= 1
        return None

    def loud_runs(self, min_len: float = 0.12) -> list[tuple[float, float]]:
        runs, start = [], None
        for i, d in enumerate(self.db + [-120.0]):
            loud = d >= self.thr + 6.0
            if loud and start is None:
                start = i
            elif not loud and start is not None:
                if (i - start) * HOP >= min_len:
                    runs.append((start * HOP, i * HOP))
                start = None
        return runs


# ---------------------------------------------------------------- helpers

def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=index,codec_type,width,height,avg_frame_rate,"
                          "r_frame_rate,color_transfer,color_range,color_primaries,channels"
                          ":stream_side_data=rotation", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def source_fps(info: dict) -> Fraction:
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    avg, nominal = Fraction(v.get("avg_frame_rate") or "0/1"), Fraction(v.get("r_frame_rate") or "0/1")
    # iPhone MOVs report avg 85700/3571 for a nominal 24/1: keep the nominal rate when the
    # two agree within 0.5%, otherwise trust the average (upstream prefers the average).
    if nominal and avg and abs(float(avg - nominal)) / float(nominal) < 0.005:
        return nominal
    return avg or nominal or Fraction(24)


def is_portrait(info: dict) -> bool:
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    w, h = int(v["width"]), int(v["height"])
    rot = next((sd.get("rotation") for sd in v.get("side_data_list") or [] if sd.get("rotation") is not None), 0)
    if int(round(float(rot))) % 180 == 90:
        w, h = h, w
    return h > w


def load_tokens(edit_dir: Path, name: str) -> list[dict]:
    p = edit_dir / "transcripts" / f"{name}.json"
    if not p.exists():
        sys.exit(f"no cached transcript {p}; run transcribe.py first")
    toks = [w for w in json.loads(p.read_text()).get("words", [])
            if w.get("type") in ("word", "audio_event") and w.get("start") is not None]
    return sorted(toks, key=lambda w: w["start"])


def parse_drop(spec: str) -> tuple[str, float, float, str]:
    m = re.fullmatch(r"([^:]+):([0-9.]+)-([0-9.]+)(?::(.*))?", spec)
    if not m:
        sys.exit(f"bad --drop {spec!r}; want NAME:START-END[:why]")
    return m.group(1), float(m.group(2)), float(m.group(3)), (m.group(4) or "drop").strip()


# ---------------------------------------------------------------- edges

def place_out(a_end: float, zone_hi: float, env: Envelope, pad: float) -> tuple[float, list[str]]:
    """Out edge after the last kept word (Scribe end a_end), never past the next token."""
    flags = []
    lo, hi = a_end + PAD_MIN, min(a_end + PAD_MAX, zone_hi - 0.005)
    if hi < lo:
        # the 30 ms pad cannot fit: no legal edge exists, so take the quietest point
        # between the words and flag it (the fix is to keep the line, see SKILL.md)
        flags.append(f"tight: only {1000 * (zone_hi - a_end):.0f} ms to the next token, pad rule cannot hold")
        t = env.quietest(a_end, zone_hi, env.before)
        return (t if t is not None else (a_end + zone_hi) / 2), flags
    edge = min(max(a_end + pad, lo), hi)
    off = env.offset_after(a_end - 0.05, hi)
    if off is None:
        # no pause at all (the speaker ran straight into the removed word): the quietest point
        # that still keeps the 30 ms pad and stays short of the next token
        flags.append("speech energy through the whole out window")
        t = env.quietest(lo, hi, env.before)
        edge = t if t is not None else hi
    elif off + PAD_MIN > edge:
        edge = min(off + PAD_MIN, hi)          # Scribe ended early: follow the audio
    return edge, flags


def place_in(c_start: float, zone_lo: float, env: Envelope, pad: float) -> tuple[float, list[str]]:
    """In edge before the first kept word (Scribe start c_start), never before the previous token."""
    flags = []
    lo, hi = max(c_start - PAD_MAX, zone_lo + 0.005), c_start - PAD_MIN
    if hi < lo:
        flags.append(f"tight: only {1000 * (c_start - zone_lo):.0f} ms after the previous token, pad rule cannot hold")
        t = env.quietest(zone_lo, c_start, env.at)
        return (t if t is not None else (zone_lo + c_start) / 2), flags
    edge = min(max(c_start - pad, lo), hi)
    on = env.onset_before(c_start + 0.05, lo)
    if on is None:
        flags.append("speech energy through the whole in window")
        t = env.quietest(lo, hi, env.at)
        edge = t if t is not None else lo
    elif on - PAD_MIN < edge:
        edge = max(on - PAD_MIN, lo)            # Scribe started late: follow the audio
    return max(0.0, edge), flags


def snap_to_frames(r: dict, fps: Fraction) -> None:
    """Make the range a whole number of frames long by moving its END inside the legal out
    window (30 to 200 ms after the last word, short of the next token), so render's own
    frame rounding has nothing left to move. Flags the range when no frame end fits."""
    last_end, zone_hi = r["last_word"][1], r["zone"][1]
    lo, hi = last_end + PAD_MIN, min(last_end + PAD_MAX, zone_hi - 0.005)
    n0 = max(1, round((r["end"] - r["start"]) * fps))
    ends = [(r["start"] + float(Fraction(n) / fps), n) for n in range(max(1, n0 - 2), n0 + 3)]
    legal = [e for e, _ in ends if lo - 1e-6 <= e <= hi + 1e-6]
    if legal:
        r["end"] = min(legal, key=lambda e: abs(e - r["end"]))
    else:
        r["flags"].append(f"out: pad rule cannot hold on the {fps} fps frame grid (no whole-frame "
                          f"end {1000 * PAD_MIN:.0f} ms or more after the word and short of the next token)")


# ---------------------------------------------------------------- words

def cmd_words(args) -> None:
    edit_dir = Path(args.edit_dir).expanduser().resolve()
    p = edit_dir / "transcripts" / f"{args.source}.json"
    for w in json.loads(p.read_text()).get("words", []):
        if w.get("end", 0) < args.start or w.get("start", 0) > args.end:
            continue
        if w.get("type") == "spacing":
            gap = w["end"] - w["start"]
            if gap >= 0.1:
                print(f"            gap {gap:.2f}s")
            continue
        print(f"  {w['start']:7.2f}-{w['end']:7.2f}  {w.get('type', 'word')[:5]:5}  {w['text'].strip()}")


# ---------------------------------------------------------------- plan

def cmd_plan(args) -> None:
    edit_dir = Path(args.edit_dir).expanduser().resolve()
    sources: dict[str, str] = {}
    for spec in args.source:
        if "=" in spec:
            name, path = spec.split("=", 1)
        else:
            path, name = spec, Path(spec).stem
        p = Path(path).expanduser().resolve()
        if not p.exists():
            sys.exit(f"source not found: {p}")
        if name in sources:
            sys.exit(f"two sources named {name!r}; name them apart with NAME=PATH")
        sources[name] = str(p)
    drops = [parse_drop(d) for d in args.drop]
    # the frame grid render will use (it takes the first source's rate unless --fps)
    grid = Fraction(args.fps) if args.fps else source_fps(probe(Path(next(iter(sources.values())))))
    for n, *_ in drops:
        if n not in sources:
            sys.exit(f"--drop names unknown source {n!r}")

    ranges, removed, flagged, timing = [], [], 0, {"onset_ms": [], "offset_ms": []}
    unlabeled: list[dict] = []
    kept_pauses: list[dict] = []
    for name, path in sources.items():
        toks = load_tokens(edit_dir, name)
        env = Envelope(Path(path))
        dur = float(probe(Path(path))["format"]["duration"])
        keep = []
        for w in toks:
            mid = (w["start"] + w["end"]) / 2
            why = None
            if w["type"] == "word" and is_filler(w) and not args.keep_fillers:
                why = "filler"
            elif w["type"] == "audio_event" and "laugh" not in w["text"].lower() and not args.keep_events:
                why = "audio event"
            for n, a, b, label in drops:
                if n == name and a <= mid <= b:
                    why = f"drop: {label}"
            keep.append(why is None)
            if why:
                removed.append({"source": name, "start": w["start"], "end": w["end"],
                                "text": w["text"].strip(), "why": why})

        # runs of kept tokens, split at a removed token or at a gap >= max_gap;
        # split_why[k] is the reason for the boundary after runs[k]
        runs, cur, split_why = [], [], []
        for i, w in enumerate(toks):
            if not keep[i]:
                if cur:
                    runs.append(cur)
                    split_why.append("removed")
                cur = []
                continue
            if cur and w["start"] - toks[cur[-1]]["end"] >= args.max_gap:
                runs.append(cur)
                split_why.append("gap")
                cur = []
            cur.append(i)
        if cur:
            runs.append(cur)

        placed = []
        for run in runs:
            a, b = toks[run[0]], toks[run[-1]]
            zone_lo = toks[run[0] - 1]["end"] if run[0] > 0 else 0.0
            zone_hi = toks[run[-1] + 1]["start"] if run[-1] + 1 < len(toks) else dur
            t_in, f_in = place_in(a["start"], zone_lo, env, args.pad_in)
            t_out, f_out = place_out(b["end"], zone_hi, env, args.pad_out)
            flags = [f"in: {f}" for f in f_in] + [f"out: {f}" for f in f_out]
            for label, level in (("in", env.at(t_in)), ("out", env.before(t_out))):
                if level >= env.thr:
                    flags.append(f"{label}: the fade at this edge covers {level:.1f} dBFS, above the {env.thr:.1f} quiet line")
            placed.append({"source": name, "start": t_in, "end": t_out,
                           "first_word": [a["start"], a["end"]], "last_word": [b["start"], b["end"]],
                           "zone": [zone_lo, zone_hi],
                           "quote": " ".join(toks[i]["text"].strip() for i in run), "flags": flags})

        # A Scribe gap can overstate the silence (a drawn-out word, an early onset). When the
        # audio-placed edges would remove less than a dead-air gap's worth, keep the pause:
        # a jump cut to save 130 ms costs more than it gains (seen on a real take: "work ... with").
        min_removed = args.max_gap - args.pad_in - args.pad_out

        def join(left: dict, right: dict, why: str) -> None:
            kept_pauses.append({"source": name, "at": round(left["last_word"][1], 2), "why": why,
                                "scribe_gap": round(right["first_word"][0] - left["last_word"][1], 2),
                                "would_remove": round(right["start"] - left["end"], 3)})
            left["end"], left["last_word"], left["zone"][1] = right["end"], right["last_word"], right["zone"][1]
            left["quote"] += " " + right["quote"]
            left["flags"] = [f for f in left["flags"] if not f.startswith("out:")] + \
                            [f for f in right["flags"] if f.startswith("out:")]

        merged, kinds = placed[:1], []           # kinds[j]: why merged[j] and merged[j+1] are apart
        for k in range(1, len(placed)):
            prev, nxt = merged[-1], placed[k]
            if split_why[k - 1] == "gap" and nxt["start"] - prev["end"] < min_removed:
                join(prev, nxt, "shorter than a dead-air gap on the audio")
                continue
            kinds.append(split_why[k - 1])
            merged.append(nxt)

        # A fragment under MIN_SEG between two cuts ("in", "at," on a real take) reads as a
        # double jump cut. Keep the pause on its gap side (the shorter one when both are gaps).
        # Drop-side boundaries are never re-joined: dropped words must stay out.
        j = 0
        while j < len(merged):
            r = merged[j]
            short = r["end"] - r["start"] < args.min_seg
            left_gap = j >= 1 and kinds[j - 1] == "gap"
            right_gap = j < len(kinds) and kinds[j] == "gap"
            if not short or not (left_gap or right_gap):
                j += 1
                continue
            left_len = r["start"] - merged[j - 1]["end"]
            right_len = merged[j + 1]["start"] - r["end"] if right_gap else float("inf")
            if left_gap and left_len <= right_len:
                join(merged[j - 1], r, f"fragment '{r['quote']}' under {args.min_seg}s between cuts")
                del merged[j], kinds[j - 1]
            else:
                join(r, merged[j + 1], f"fragment '{r['quote']}' under {args.min_seg}s between cuts")
                del merged[j + 1], kinds[j]
            j = max(0, j - 1)

        for r in merged:
            # start is rounded BEFORE the snap, so plan and render compute the same frame end
            r["start"] = round(r["start"], 4)
            snap_to_frames(r, grid)
            r["end"] = round(r["end"], 6)
            flagged += bool(r["flags"])
        # after the snap, so the reported dead air matches the ranges that render will cut
        for j, why in enumerate(kinds):
            if why == "gap":
                prev, nxt = merged[j], merged[j + 1]
                removed.append({"source": name, "start": prev["end"], "end": nxt["start"],
                                "text": "", "why": f"dead air {nxt['start'] - prev['end']:.2f}s cut "
                                                   f"(Scribe gap {nxt['first_word'][0] - prev['last_word'][1]:.2f}s)"})
        ranges += merged

        # Scribe vs RMS timing, measured only where a word stands clear of its neighbours
        for i, w in enumerate(toks):
            if w["type"] != "word":
                continue
            prev_end = toks[i - 1]["end"] if i else 0.0
            next_start = toks[i + 1]["start"] if i + 1 < len(toks) else dur
            if w["start"] - prev_end >= 0.25:
                on = env.onset_before(min(w["end"], w["start"] + 0.3), max(prev_end, w["start"] - 0.25))
                if on is not None:
                    timing["onset_ms"].append(round(1000 * (w["start"] - on)))
            if next_start - w["end"] >= 0.25:
                off = env.offset_after(max(w["start"], w["end"] - 0.3), min(next_start, w["end"] + 0.25))
                if off is not None:
                    timing["offset_ms"].append(round(1000 * (off - w["end"])))

        # sound the transcript does not account for: a filler Scribe normalized away, a
        # breath, a knock. Listed for a timeline_view drill-down, never cut automatically.
        for s, e in env.loud_runs():
            if not any(w["start"] - 0.05 < e and w["end"] + 0.05 > s for w in toks):
                unlabeled.append({"source": name, "start": round(s, 2), "end": round(e, 2),
                                  "peak_db": round(max(env.db[env.idx(s):env.idx(e) + 1]), 1)})
        print(f"{name}: envelope noise {env.noise:.1f} dBFS, speech {env.speech:.1f}, quiet line {env.thr:.1f}")

    def stats(xs: list[int]) -> dict:
        if not xs:
            return {"n": 0}
        a = sorted(abs(x) for x in xs)
        return {"n": len(xs), "median": statistics.median(xs), "median_abs": statistics.median(a),
                "p90_abs": a[int(0.9 * (len(a) - 1))], "max_abs": a[-1]}

    timing_summary = {"onset_scribe_minus_rms_ms": stats(timing["onset_ms"]),
                      "offset_rms_minus_scribe_ms": stats(timing["offset_ms"])}
    edl = {"version": 1, "tool": "rough_cut.py", "sources": sources,
           "params": {"pad_in": args.pad_in, "pad_out": args.pad_out, "max_gap": args.max_gap,
                      "min_seg": args.min_seg, "fps": f"{grid.numerator}/{grid.denominator}",
                      "fade": FADE, "drops": [list(d) for d in drops]},
           "ranges": ranges, "removed": removed, "kept_pauses": kept_pauses, "unlabeled_sound": unlabeled,
           "scribe_vs_rms": timing_summary}
    out = edit_dir / "edl.json"
    out.write_text(json.dumps(edl, indent=2))

    src_total = sum(float(probe(Path(p))["format"]["duration"]) for p in sources.values())
    kept = sum(r["end"] - r["start"] for r in ranges)
    kinds: dict[str, int] = {}
    for r in removed:
        k = r["why"] if r["why"].startswith("drop") else ("dead air" if r["why"].startswith("dead air") else r["why"])
        kinds[k] = kinds.get(k, 0) + 1
    print(f"plan -> {out}")
    print(f"  {len(ranges)} ranges, {max(0, len(ranges) - 1)} cuts, source {src_total:.2f}s -> about {kept:.2f}s")
    print("  removed: " + (", ".join(f"{k} x{v}" for k, v in sorted(kinds.items())) or "nothing"))
    if kept_pauses:
        print(f"  pauses kept ({len(kept_pauses)}):")
        for kp in kept_pauses:
            print(f"    {kp['source']} {kp['at']:.2f}: {kp['why']} (would have removed {kp['would_remove']:.2f}s)")
    print(f"  edges flagged for a drill-down: {flagged}")
    for r in ranges:
        if r["flags"]:
            print(f"    {r['source']} {r['start']:.2f}-{r['end']:.2f}: {'; '.join(r['flags'])}")
    if unlabeled:
        print(f"  unlabeled sound (no transcript token, check with timeline_view): "
              + ", ".join(f"{u['source']} {u['start']:.2f}-{u['end']:.2f} ({u['peak_db']} dB)" for u in unlabeled))
    print(f"  Scribe vs RMS: onsets {timing_summary['onset_scribe_minus_rms_ms']}, "
          f"offsets {timing_summary['offset_rms_minus_scribe_ms']}")


# ---------------------------------------------------------------- render

def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed ({r.returncode}): {' '.join(cmd[:6])} ...\n{r.stderr[-1500:]}")


def ebur128(path: Path) -> dict:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
                        "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    get = lambda pat: (lambda m: float(m.group(1)) if m else None)(re.search(pat, tail, re.S))
    return {"integrated_lufs": get(r"I:\s+(-?[\d.]+) LUFS"), "lra_lu": get(r"LRA:\s+(-?[\d.]+) LU"),
            "true_peak_dbtp": get(r"True peak:\s+Peak:\s+(-?[\d.]+) dBFS")}


def stream_durations(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration,nb_frames",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return {s["codec_type"]: {"duration": float(s.get("duration", 0)), "nb_frames": int(s.get("nb_frames", 0) or 0)}
            for s in json.loads(out.stdout)["streams"]}


def cmd_render(args) -> None:
    edit_dir = Path(args.edit_dir).expanduser().resolve()
    edl = json.loads((edit_dir / "edl.json").read_text())
    sources = {k: Path(v) for k, v in edl["sources"].items()}
    infos = {k: probe(p) for k, p in sources.items()}
    for k, info in infos.items():
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        if v.get("color_transfer") in ("arib-std-b67", "smpte2084"):
            sys.exit(f"{k} is HDR ({v['color_transfer']}); this ffmpeg has no zscale to tone-map it. "
                     "Ask for an SDR export (iPhone: Settings > Camera > Record Video > HDR Video off).")
    first = next(iter(sources))
    fps = Fraction(args.fps) if args.fps else source_fps(infos[first])
    planned = edl.get("params", {}).get("fps")
    if planned and Fraction(planned) != fps:
        print(f"note: edl.json was snapped to {planned} fps, rendering at {fps.numerator}/{fps.denominator}; "
              "re-plan with the same --fps to keep every pad")
    ranges = edl["ranges"]
    if not ranges:
        sys.exit("edl.json has no ranges")

    # Hard Rule: never cut inside a word. Re-checked here because edl.json is hand-editable.
    tok_cache = {k: load_tokens(edit_dir, k) for k in sources}
    for r in ranges:
        for edge in (r["start"], r["end"]):
            inside = [w for w in tok_cache[r["source"]] if w["type"] == "word" and w["start"] + 0.01 < edge < w["end"] - 0.01]
            if inside:
                sys.exit(f"edge {edge:.3f} in {r['source']} falls inside the word '{inside[0]['text'].strip()}' "
                         f"({inside[0]['start']:.2f}-{inside[0]['end']:.2f}); fix edl.json or re-plan")

    # whole-frame segment lengths: audio and video then stay aligned across any number of cuts
    segs = []
    for i, r in enumerate(ranges):
        n = max(1, round((r["end"] - r["start"]) * fps))
        end_q = r["start"] + n / fps
        last_end, zone_hi = r["last_word"][1], r["zone"][1]
        # plan already snapped ends to this grid; these only act on a hand-edited edl.json
        # or a --fps override, and they hold the same 30 ms pad the plan does
        # (same 1e-6 tolerance as snap_to_frames, so a plan-snapped end is never re-rounded)
        if float(end_q) < last_end + PAD_MIN - 1e-6 and float(r["start"] + (n + 1) / fps) <= zone_hi + 1e-6:
            n += 1
        elif float(end_q) > zone_hi + 1e-6 and float(r["start"] + (n - 1) / fps) >= last_end + PAD_MIN - 1e-6:
            n -= 1
        segs.append({"i": i, "source": r["source"], "start": r["start"], "frames": n, "dur": float(Fraction(n) / fps)})

    seg_dir = edit_dir / "segments"
    seg_dir.mkdir(exist_ok=True)
    for old in seg_dir.glob("seg_*.mov"):
        old.unlink()
    height = args.height

    def extract(s: dict) -> Path:
        info = infos[s["source"]]
        scale = f"scale=-2:{height}" if is_portrait(info) else f"scale={height}:-2"
        out = seg_dir / f"seg_{s['i']:03d}.mov"
        d = s["dur"]
        af = (f"asetpts=PTS-STARTPTS,aresample=48000,apad,atrim=0:{d:.6f},"
              f"afade=t=in:st=0:d={FADE},afade=t=out:st={max(0.0, d - FADE):.6f}:d={FADE}")
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{s['start']:.4f}", "-i", str(sources[s["source"]]),
             "-map", "0:v:0", "-map", "0:a:0",
             "-vf", f"setpts=PTS-STARTPTS,{scale}:flags=lanczos,fps={fps.numerator}/{fps.denominator},format=yuv420p",
             "-frames:v", str(s["frames"]), "-af", af,
             "-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf),
             "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
             "-c:a", "pcm_s16le", "-ar", "48000", str(out)])
        return out

    print(f"extracting {len(segs)} segment(s) at {fps.numerator}/{fps.denominator} fps, CRF {args.crf}")
    with ThreadPoolExecutor(max_workers=3) as ex:
        paths = list(ex.map(extract, segs))

    lst = edit_dir / "segments" / "concat.txt"
    # concat demuxer quoting: a literal ' closes the string, so write it as '\''
    lst.write_text("".join("file '" + str(p).replace("'", "'\\''") + "'\n" for p in paths))
    master = edit_dir / "rough_cut_master.mov"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(master)])
    final = edit_dir / (args.output or "rough_cut.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(master), "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)])

    # Hard Rule: output-timeline offsets. output_time = word.start - seg.start + seg.offset
    words_out, cuts, offset = [], [], 0.0
    for s, r in zip(segs, ranges):
        seg_end_src = s["start"] + s["dur"]
        for w in tok_cache[s["source"]]:
            # any word OVERLAPPING the segment, so a word an edge clips at either end still
            # shows up here and verify flags it as a word across the cut
            if w["end"] > s["start"] + 1e-6 and w["start"] < seg_end_src - 1e-6:
                words_out.append({"type": w["type"], "text": w["text"], "source": s["source"],
                                  "start": round(w["start"] - s["start"] + offset, 3),
                                  "end": round(w["end"] - s["start"] + offset, 3)})
        if s["i"] > 0:
            prev = ranges[s["i"] - 1]
            cuts.append({"index": s["i"], "t": round(offset, 3),
                         "from": {"source": prev["source"], "src_end": round(segs[s["i"] - 1]["start"] + segs[s["i"] - 1]["dur"], 3)},
                         "to": {"source": s["source"], "src_start": round(s["start"], 3)}})
        offset += s["dur"]
    (edit_dir / "cut_words.json").write_text(json.dumps({"words": words_out}, indent=2))
    (edit_dir / "cuts.json").write_text(json.dumps(cuts, indent=2))

    expected = sum(s["dur"] for s in segs)
    streams = stream_durations(final)
    src_total = sum(float(i["format"]["duration"]) for i in infos.values())
    report = {"output": str(final), "fps": f"{fps.numerator}/{fps.denominator}", "segments": len(segs),
              "cuts": len(cuts), "source_duration_s": round(src_total, 3), "expected_duration_s": round(expected, 3),
              "expected_frames": sum(s["frames"] for s in segs), "streams": streams,
              "av_diff_ms": round(1000 * (streams["audio"]["duration"] - streams["video"]["duration"]), 1),
              "loudness_source": ebur128(sources[first]) if len(sources) == 1 else None,
              "loudness_output": ebur128(final)}
    (edit_dir / "render_report.json").write_text(json.dumps(report, indent=2))
    lo = report["loudness_output"]
    print(f"rendered {final}")
    print(f"  {src_total:.2f}s -> {streams['video']['duration']:.3f}s video / {streams['audio']['duration']:.3f}s audio "
          f"(expected {expected:.3f}s, {report['expected_frames']} frames, got {streams['video']['nb_frames']})")
    print(f"  {len(cuts)} cuts, A/V diff {report['av_diff_ms']} ms")
    print(f"  loudness {lo['integrated_lufs']} LUFS, true peak {lo['true_peak_dbtp']} dBTP"
          + ("  <- above -1 dBTP, leave headroom before mastering" if (lo["true_peak_dbtp"] or -99) > -1 else ""))


# ---------------------------------------------------------------- verify

def cmd_verify(args) -> None:
    from timeline_view import read_pcm, render_timeline

    edit_dir = Path(args.edit_dir).expanduser().resolve()
    video = edit_dir / (args.video or "rough_cut.mp4")
    cuts = json.loads((edit_dir / "cuts.json").read_text())
    words = [w for w in json.loads((edit_dir / "cut_words.json").read_text())["words"] if w["type"] == "word"]
    dur = float(probe(video)["format"]["duration"])
    vdir = edit_dir / "verify"
    vdir.mkdir(exist_ok=True)
    # only this command's own outputs; drill down PNGs saved here survive
    for old in [*vdir.glob("cut_*.png"), vdir / "head.png", vdir / "tail.png"]:
        old.unlink(missing_ok=True)

    pcm = read_pcm(video, 0.0, dur)
    sr = 16000

    def rms_db(t0: float, t1: float) -> float:
        a, b = max(0, int(t0 * sr)), min(len(pcm), int(t1 * sr))
        if b <= a:
            return -120.0
        r = math.sqrt(sum(s * s for s in pcm[a:b]) / (b - a)) / 32768.0
        return 20 * math.log10(r) if r > 0 else -120.0

    all_t = [c["t"] for c in cuts]
    rows, flagged = [], 0
    for c in cuts:
        t = c["t"]
        a, b = max(0.0, t - 1.5), min(dur, t + 1.5)
        png = vdir / f"cut_{c['index']:02d}_{t:07.2f}.png"
        res = render_timeline(video, a, b, png, 10, edit_dir / "cut_words.json",
                              [x for x in all_t if a <= x <= b], title=f"cut {c['index']}/{len(cuts)}")
        local = sorted(rms_db(x / 100, x / 100 + 0.01) for x in range(int(a * 100), int(b * 100)))
        local_speech = local[int(0.9 * (len(local) - 1))] if local else -120.0
        at_cut = rms_db(t - 0.005, t + 0.005)
        # the outer halves of the two 30 ms fades (gain 1 to 0.5): speech-level energy here
        # means the fade is eating a word. Speech starting right AFTER the fade-in is normal.
        edge_before, edge_after = rms_db(t - FADE, t - FADE / 2), rms_db(t + FADE / 2, t + FADE)
        before = [w for w in words if w["end"] <= t + 1e-6]
        after = [w for w in words if w["start"] >= t - 1e-6]
        straddle = [w for w in words if w["start"] < t - 0.001 and w["end"] > t + 0.001]
        gap_b = round(1000 * (t - before[-1]["end"])) if before else None
        gap_a = round(1000 * (after[0]["start"] - t)) if after else None
        lum = res["frame_luma"]
        flags = []
        if straddle:
            flags.append(f"word across the cut: {straddle[0]['text'].strip()}")
        pad_ms = round(1000 * PAD_MIN)
        if gap_b is not None and gap_b < pad_ms:
            flags.append(f"only {gap_b} ms after the last word (pad rule: {pad_ms} ms)")
        if gap_a is not None and gap_a < pad_ms:
            flags.append(f"only {gap_a} ms before the next word (pad rule: {pad_ms} ms)")
        if max(edge_before, edge_after) > local_speech - 12:
            flags.append(f"speech-level energy inside a fade ({max(edge_before, edge_after):.1f} vs {local_speech:.1f} dB): clipped word?")
        if at_cut > local_speech - 20:
            flags.append(f"loud at the cut instant ({at_cut:.1f} dB): fade missing?")
        if min(lum) < 16:
            flags.append(f"dark frame (luma {min(lum)})")
        if max(abs(lum[i + 1] - lum[i]) for i in range(len(lum) - 1)) > 40:
            flags.append("luma jump > 40 between frames (flash?)")
        flagged += bool(flags)
        rows.append({"index": c["index"], "t": t, "png": png.name, "gap_before_ms": gap_b, "gap_after_ms": gap_a,
                     "cut_db": round(at_cut, 1), "edge_db": [round(edge_before, 1), round(edge_after, 1)],
                     "local_speech_db": round(local_speech, 1), "frame_luma": lum, "flags": flags})

    render_timeline(video, 0.0, min(dur, 2.0), vdir / "head.png", 8, edit_dir / "cut_words.json", all_t, "head")
    render_timeline(video, max(0.0, dur - 2.0), dur, vdir / "tail.png", 8, edit_dir / "cut_words.json", all_t, "tail")

    lines = ["# Cut boundary self check", "", f"Video: {video}", f"Boundaries: {len(cuts)}, flagged: {flagged}", "",
             "| # | t (s) | gap before ms | gap after ms | dB at cut | dB in fade out / fade in | local speech dB | flags |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['index']} | {r['t']:.2f} | {r['gap_before_ms']} | {r['gap_after_ms']} | {r['cut_db']} | "
                     f"{r['edge_db'][0]} / {r['edge_db'][1]} | {r['local_speech_db']} | {'; '.join(r['flags']) or 'ok'} |")
    (vdir / "report.md").write_text("\n".join(lines) + "\n")
    (vdir / "report.json").write_text(json.dumps(rows, indent=2))
    print(f"verify -> {vdir}: {len(cuts)} boundaries, {flagged} flagged, plus head.png and tail.png")
    for r in rows:
        if r["flags"]:
            print(f"  cut {r['index']} at {r['t']:.2f}s: {'; '.join(r['flags'])}")
    sys.exit(1 if flagged else 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("words")
    w.add_argument("edit_dir")
    w.add_argument("source")
    w.add_argument("start", type=float)
    w.add_argument("end", type=float)

    p = sub.add_parser("plan")
    p.add_argument("--edit-dir", required=True)
    p.add_argument("--source", action="append", required=True, help="NAME=PATH or PATH (name = file stem); order = output order")
    p.add_argument("--drop", action="append", default=[], help="NAME:START-END[:why], source seconds; words whose midpoint falls inside are removed")
    p.add_argument("--max-gap", type=float, default=MAX_GAP)
    p.add_argument("--min-seg", type=float, default=MIN_SEG)
    p.add_argument("--fps", default=None, help="Frame grid to snap to; pass the same value to render")
    p.add_argument("--pad-in", type=float, default=PAD_IN)
    p.add_argument("--pad-out", type=float, default=PAD_OUT)
    p.add_argument("--keep-fillers", action="store_true")
    p.add_argument("--keep-events", action="store_true")

    r = sub.add_parser("render")
    r.add_argument("--edit-dir", required=True)
    r.add_argument("--crf", type=int, default=16)
    r.add_argument("--fps", default=None, help="Override, e.g. 30 or 30000/1001")
    r.add_argument("--height", type=int, default=1920, help="Long edge in px (1920 gives 1080x1920 portrait)")
    r.add_argument("-o", "--output", default=None, help="File name inside the edit dir (default rough_cut.mp4)")

    v = sub.add_parser("verify")
    v.add_argument("--edit-dir", required=True)
    v.add_argument("--video", default=None)

    args = ap.parse_args()
    for pad in ("pad_in", "pad_out"):
        if hasattr(args, pad) and not (PAD_MIN <= getattr(args, pad) <= PAD_MAX):
            sys.exit(f"--{pad.replace('_', '-')} must stay inside the {PAD_MIN * 1000:.0f} to {PAD_MAX * 1000:.0f} ms window")
    {"words": cmd_words, "plan": cmd_plan, "render": cmd_render, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    main()
