#!/usr/bin/env python3
"""Choose the sections of a song most likely to perform in short-form video.

Implements the evidence-backed heuristics from docs/viral-strategy research:
  1. Generate multiple candidate windows (not one): chorus/repetition peaks,
     energy-rise transitions (build->drop), artist TikTok-start prior.
  2. The hook must land in the first ~3s of the clip -> windows start on the
     downbeat at/just before the anchor.
  3. 15-30s windows with a strong short core.
  4. Prefer windows containing a quotable lyric line near the start.
  5. Prefer windows with a contrast/transition (energy rise).
  6. Score loopability (end flows back into start).

Inputs reuse the beat-synced-codex-edit-kit analysis outputs (beats/sections
CSVs) when available; chroma self-similarity (RefraiD-style repetition) is
computed here directly.

Usage:
  choose_viral_window.py --audio song.wav [--analysis-dir DIR]
      [--transcript whisper.json] [--tiktok-start 15.0]
      [--durations 15,22,30] [--out outdir]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np

import librosa

SR = 22050
HOP = 512

EMOTIONAL_WORDS = {
    "love", "miss", "hate", "cry", "alone", "lonely", "heart", "broken",
    "night", "feel", "feelings", "hurt", "sorry", "stay", "leave", "home",
    "lost", "save", "saved", "wait", "run", "hold", "never", "always",
    "nothing", "empty", "hollow", "dream", "sleep", "die", "breathe", "you",
}


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    y, sr = librosa.load(str(path), sr=SR, mono=True)
    return y, sr


def beat_grid(y: np.ndarray, sr: int) -> tuple[float, np.ndarray]:
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=HOP)
    times = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)
    if np.ndim(tempo):
        tempo = float(np.atleast_1d(tempo)[0])
    return float(tempo), times


def energy_curve(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP)
    lo, hi = np.percentile(rms, [5, 95])
    norm = np.clip((rms - lo) / max(hi - lo, 1e-9), 0, 1)
    return t, norm


def repetition_score(y: np.ndarray, sr: int, beat_times: np.ndarray) -> np.ndarray:
    """Per-beat chorus-ness: how strongly does this beat's chroma recur
    elsewhere in the song (time-lag structure, RefraiD-lite)."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
    beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=HOP)
    beat_frames = np.clip(beat_frames, 0, chroma.shape[1] - 1)
    sync = librosa.util.sync(chroma, beat_frames, aggregate=np.median)
    sync = librosa.util.normalize(sync, axis=0)
    n = sync.shape[1]
    if n < 8:
        return np.zeros(n)
    ssm = sync.T @ sync  # cosine-ish similarity, beats x beats
    np.fill_diagonal(ssm, 0.0)
    # suppress the near-diagonal (trivial self-similarity of neighbors)
    for k in range(1, min(8, n)):
        idx = np.arange(n - k)
        ssm[idx, idx + k] = 0.0
        ssm[idx + k, idx] = 0.0
    rep = ssm.mean(axis=1)
    lo, hi = np.percentile(rep, [5, 95])
    return np.clip((rep - lo) / max(hi - lo, 1e-9), 0, 1)


def loop_seam(y: np.ndarray, sr: int, start: float, end: float) -> float:
    """Similarity of the audio right after `end` wrapping to right after
    `start` — how invisible would the loop cut be."""
    dur = 1.0
    a0, a1 = int(start * sr), int((start + dur) * sr)
    b0, b1 = int(end * sr), int((end + dur) * sr)
    if b1 > len(y) or a1 > len(y):
        return 0.0
    fa = np.concatenate([
        librosa.feature.chroma_cqt(y=y[a0:a1], sr=sr).mean(axis=1),
        librosa.feature.mfcc(y=y[a0:a1], sr=sr, n_mfcc=13).mean(axis=1),
    ])
    fb = np.concatenate([
        librosa.feature.chroma_cqt(y=y[b0:b1], sr=sr).mean(axis=1),
        librosa.feature.mfcc(y=y[b0:b1], sr=sr, n_mfcc=13).mean(axis=1),
    ])
    denom = np.linalg.norm(fa) * np.linalg.norm(fb)
    if denom < 1e-9:
        return 0.0
    return float(np.dot(fa, fb) / denom)


def load_transcript(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text())
    segs = data.get("segments") or []
    out = []
    for s in segs:
        text = (s.get("text") or "").strip()
        if text:
            out.append({"start": float(s["start"]), "end": float(s["end"]), "text": text})
    return out


def lyric_score(segs: list[dict], start: float, end: float) -> tuple[float, str]:
    """Reward a complete lyric phrase starting within the first 3s of the
    window; bonus for emotional/quotable vocabulary."""
    best, best_text = 0.0, ""
    for s in segs:
        if start - 0.5 <= s["start"] <= start + 3.0 and s["end"] <= end + 1.0:
            words = set(re.findall(r"[a-z']+", s["text"].lower()))
            emo = len(words & EMOTIONAL_WORDS)
            score = 0.6 + min(emo * 0.13, 0.4)
            if score > best:
                best, best_text = score, s["text"]
    return best, best_text


def interp(t: np.ndarray, v: np.ndarray, at: float) -> float:
    return float(np.interp(at, t, v))


def window_mean(t: np.ndarray, v: np.ndarray, a: float, b: float) -> float:
    mask = (t >= a) & (t <= b)
    return float(v[mask].mean()) if mask.any() else 0.0


def snap_to_grid(anchor: float, beat_times: np.ndarray, beats_per_bar: int = 4) -> float:
    """Snap to the bar downbeat at/just before the anchor so the hook lands
    inside the first seconds of the clip."""
    downbeats = beat_times[::beats_per_bar]
    prior = downbeats[downbeats <= anchor + 0.05]
    return float(prior[-1]) if len(prior) else max(0.0, anchor)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, type=Path)
    ap.add_argument("--transcript", type=Path, default=None)
    ap.add_argument("--tiktok-start", type=float, default=None,
                    help="artist-chosen TikTok start time in seconds (prior)")
    ap.add_argument("--durations", default="15,22,30")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--top", type=int, default=3)
    args = ap.parse_args()

    durations = [float(d) for d in args.durations.split(",")]
    y, sr = load_audio(args.audio)
    total = len(y) / sr
    tempo, beat_times = beat_grid(y, sr)
    t_e, energy = energy_curve(y, sr)
    rep = repetition_score(y, sr, beat_times)
    segs = load_transcript(args.transcript)

    # --- anchors ---------------------------------------------------------
    anchors: dict[float, str] = {}

    def add(anchor: float, reason: str) -> None:
        if 0 <= anchor < total - min(durations):
            key = round(snap_to_grid(anchor, beat_times), 3)
            if key not in anchors:
                anchors[key] = reason

    # (a) repetition (chorus-ness) peaks
    order = np.argsort(rep)[::-1]
    picked = []
    for bi in order:
        bt = beat_times[bi] if bi < len(beat_times) else None
        if bt is None:
            continue
        if all(abs(bt - p) > 8.0 for p in picked):
            picked.append(bt)
            add(bt, "chorus/repetition peak")
        if len(picked) >= 4:
            break

    # (b) energy-rise transitions (build -> drop)
    win = 4.0
    rises = []
    for bt in beat_times:
        pre = window_mean(t_e, energy, bt - win, bt)
        post = window_mean(t_e, energy, bt, bt + win)
        rises.append(post - pre)
    rises = np.array(rises)
    picked_r = []
    for bi in np.argsort(rises)[::-1]:
        bt = beat_times[bi]
        if all(abs(bt - p) > 8.0 for p in picked_r):
            picked_r.append(bt)
            add(bt, "energy rise (build->drop)")
        if len(picked_r) >= 4:
            break

    # (c) artist TikTok-start prior
    if args.tiktok_start is not None:
        add(args.tiktok_start, "artist TikTok start prior")

    # --- score windows ----------------------------------------------------
    rows = []
    for start, reason in anchors.items():
        for dur in durations:
            end = start + dur
            if end > total - 0.25:
                continue
            e_mean = window_mean(t_e, energy, start, end)
            rise = interp(np.arange(len(rises), dtype=float), rises,
                          float(np.searchsorted(beat_times, start)))
            bi0 = int(np.searchsorted(beat_times, start))
            bi1 = int(np.searchsorted(beat_times, end))
            rep_mean = float(rep[bi0:max(bi1, bi0 + 1)].mean()) if bi0 < len(rep) else 0.0
            lyr, lyr_text = lyric_score(segs, start, end)
            loop = loop_seam(y, sr, start, end)
            prior = 0.0
            if args.tiktok_start is not None and abs(start - args.tiktok_start) <= 5.0:
                prior = 1.0
            score = (0.26 * e_mean + 0.20 * rep_mean + 0.18 * max(rise, 0) * 2.0
                     + 0.16 * lyr + 0.12 * loop + 0.08 * prior)
            rows.append({
                "start_sec": round(start, 3), "end_sec": round(end, 3),
                "duration": dur, "score": round(score, 4),
                "energy": round(e_mean, 3), "repetition": round(rep_mean, 3),
                "energy_rise": round(float(rise), 3), "lyric": round(lyr, 3),
                "loop_seam": round(loop, 3), "prior": prior,
                "anchor_reason": reason, "lyric_line": lyr_text,
                "timecode": f"{int(start // 60)}:{start % 60:05.2f}",
            })

    rows.sort(key=lambda r: r["score"], reverse=True)
    # de-duplicate: keep top windows that overlap < 50% with better ones
    chosen: list[dict] = []
    for r in rows:
        ok = True
        for c in chosen:
            a = max(r["start_sec"], c["start_sec"])
            b = min(r["end_sec"], c["end_sec"])
            if max(0.0, b - a) / r["duration"] > 0.5:
                ok = False
                break
        if ok:
            chosen.append(r)
        if len(chosen) >= args.top:
            break

    result = {
        "audio": str(args.audio), "duration_sec": round(total, 2),
        "tempo_bpm": round(tempo, 2), "tiktok_start_prior": args.tiktok_start,
        "windows": chosen,
    }
    out_dir = args.out or args.audio.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.audio.stem.replace(" ", "_")
    (out_dir / f"{stem}_viral_windows.json").write_text(json.dumps(result, indent=2))
    with (out_dir / f"{stem}_viral_windows.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(chosen[0].keys()) if chosen else ["start_sec"])
        w.writeheader()
        w.writerows(chosen)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
