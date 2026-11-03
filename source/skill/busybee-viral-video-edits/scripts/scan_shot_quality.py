#!/usr/bin/env python3
"""Shot-level footage curation: the v2 quality gate.

Replaces whole-file luma gating with per-SHOT scoring. For every source file:
  1. PySceneDetect splits it into shots.
  2. Each shot is sampled at 3 frames and scored:
       - luma            (reject too dark / blown out)
       - sharpness       (Laplacian variance — reject soft/blurry)
       - text_ratio      (tesseract OCR box coverage — reject title cards,
                          intertitles, watermark-heavy frames, "mostly words")
       - colorfulness    (Hasler-Suesstrunk — flag drab)
       - motion          (mean abs frame diff inside the shot)
       - border_ratio    (black pillarbox/letterbox bars — reject)
  3. Output: shot_map.json — per file, the list of ACCEPTED shots
     (start/end/scores) the builder may cut from, plus per-file stats.

Usage: scan_shot_quality.py --root path/to/footage [--min-shot 1.2] [--jobs 3]

Requires: opencv-python, numpy, scenedetect, pytesseract (+ the tesseract
binary on PATH for text-ratio scoring — falls back to 0.0 if unavailable).
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

OUT_NAME = "shot_map.json"

# thresholds (v2 quality bar)
LUMA_LO, LUMA_HI = 28.0, 215.0
SHARP_MIN = 40.0          # Laplacian variance floor (absolute, on 480px-wide gray)
# lanes that are dark BY DESIGN get a lower luma floor — match on a substring
# of the file path, e.g. a folder named "night_drive" or "moonrise"
DARK_OK_MARKERS = ("night_drive", "cozy", "moonrise", "supermoon", "plankton")
LUMA_LO_DARK = 11.0
SHARP_MIN_BW = 16.0       # soft-focus archival film: grain-real but gentler floor
TEXT_MAX = 0.045          # max fraction of frame area covered by OCR word boxes
BORDER_MAX = 0.18         # max fraction of frame that is black border rows/cols
COLOR_MIN = 8.0           # Hasler-Suesstrunk colorfulness floor (B&W archival exempt)


def frame_metrics(frame: np.ndarray) -> dict:
    small = cv2.resize(frame, (480, int(480 * frame.shape[0] / frame.shape[1])))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    luma = float(gray.mean())
    hi_frac = float((gray > 120).mean())
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    # black borders: rows/cols with near-zero mean
    rows = gray.mean(axis=1) < 12
    cols = gray.mean(axis=0) < 12
    border = float(rows.mean() * 0.5 + cols.mean() * 0.5)
    # colorfulness (Hasler-Suesstrunk)
    b, g, r = cv2.split(small.astype(np.float32))
    rg, yb = np.abs(r - g), np.abs(0.5 * (r + g) - b)
    color = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2)
                  + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))
    return {"luma": luma, "hi_frac": hi_frac, "sharp": sharp, "border": border,
            "color": color, "_gray": gray}


def text_ratio(gray: np.ndarray) -> float:
    """Fraction of frame area covered by OCR-detected word boxes."""
    try:
        import pytesseract
        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT,
                                         config="--psm 11")
    except Exception:
        return 0.0
    area = gray.shape[0] * gray.shape[1]
    covered = 0
    for i, txt in enumerate(data["text"]):
        if txt and txt.strip() and int(data.get("conf", ["0"] * len(data["text"]))[i]) > 55:
            covered += data["width"][i] * data["height"][i]
    return covered / area


def scan_file(path: Path, min_shot: float) -> tuple[str, dict]:
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector

    video = open_video(str(path))
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=27.0, min_scene_len=int(min_shot * video.frame_rate)))
    sm.detect_scenes(video, show_progress=False)
    scenes = sm.get_scene_list()
    if not scenes:  # single-shot file (e.g., fixed-camera timelapse)
        dur = video.duration.get_seconds()
        scenes = [(video.base_timecode, video.base_timecode + dur)]

    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    accepted, rejected = [], {"dark": 0, "soft": 0, "text": 0, "border": 0, "short": 0}
    is_bw_file_votes = []

    # continuous footage (dashcams, timelapses) yields file-length "shots";
    # subdivide anything over 25s into 12s windows so each is judged locally
    spans = []
    for s0, s1 in scenes:
        t0, t1 = s0.get_seconds(), s1.get_seconds()
        if t1 - t0 > 25.0:
            t = t0
            while t < t1 - 4.0:
                spans.append((t, min(t + 12.0, t1)))
                t += 12.0
        else:
            spans.append((t0, t1))
    for t0, t1 in spans:
        if t1 - t0 < min_shot:
            rejected["short"] += 1
            continue
        samples = [t0 + (t1 - t0) * f for f in (0.2, 0.5, 0.8)]
        ms, texts = [], []
        motion_prev, motion_vals = None, []
        for t in samples:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            m = frame_metrics(frame)
            texts.append(text_ratio(m["_gray"]))
            if motion_prev is not None:
                motion_vals.append(float(np.abs(m["_gray"].astype(np.int16)
                                                - motion_prev.astype(np.int16)).mean()))
            motion_prev = m["_gray"]
            del m["_gray"]
            ms.append(m)
        if len(ms) < 3:
            continue
        luma = np.median([m["luma"] for m in ms])
        sharp = np.median([m["sharp"] for m in ms])
        border = max(m["border"] for m in ms)
        color = np.median([m["color"] for m in ms])
        text = max(texts)
        motion = float(np.mean(motion_vals)) if motion_vals else 0.0
        is_bw_file_votes.append(color < COLOR_MIN)

        dark_ok = any(m in str(path) for m in DARK_OK_MARKERS)
        hi_frac = np.median([m["hi_frac"] for m in ms])
        if dark_ok:
            # night content: needs visible highlights (streetlights, moon, fire)
            if luma > LUMA_HI or (luma < LUMA_LO_DARK and hi_frac < 0.02):
                rejected["dark"] += 1
                continue
        elif not (LUMA_LO < luma < LUMA_HI):
            rejected["dark"] += 1
            continue
        sharp_min = SHARP_MIN_BW if (color < COLOR_MIN) else SHARP_MIN
        if sharp < sharp_min:
            rejected["soft"] += 1
            continue
        if text > TEXT_MAX:
            rejected["text"] += 1
            continue
        if border > BORDER_MAX:
            rejected["border"] += 1
            continue
        accepted.append({
            "start": round(t0, 2), "end": round(t1, 2),
            "luma": round(float(luma), 1), "sharp": round(float(sharp), 1),
            "text": round(float(text), 4), "color": round(float(color), 1),
            "motion": round(motion, 2),
        })
    cap.release()
    info = {
        "duration": scenes[-1][1].get_seconds() if scenes else 0.0,
        "is_bw": bool(np.mean(is_bw_file_votes) > 0.6) if is_bw_file_votes else False,
        "shots_accepted": len(accepted),
        "shots_rejected": rejected,
        "accepted": accepted,
    }
    return str(path), info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("assets/sourced_footage"),
                    help="footage directory to scan (default: assets/sourced_footage)")
    ap.add_argument("--min-shot", type=float, default=1.2)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--also", type=Path, nargs="*", default=[],
                    help="additional dirs (e.g. an owned clip library)")
    args = ap.parse_args()

    files = sorted(args.root.rglob("*.mp4"))
    for extra in args.also:
        files += sorted(Path(extra).rglob("*.mp4"))
    files = [f for f in files if "_quarantine" not in str(f) and "_qa" not in str(f)]
    print(f"scanning {len(files)} files (shot-level)")
    result = {}
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(scan_file, f, args.min_shot): f for f in files}
        from concurrent.futures import as_completed
        for fut in as_completed(futs):
            f = futs[fut]
            try:
                path, info = fut.result()
                result[path] = info
                rej = info["shots_rejected"]
                print(f"  {f.name}: {info['shots_accepted']} shots ok "
                      f"(rejected: dark={rej['dark']} soft={rej['soft']} "
                      f"text={rej['text']} border={rej['border']})"
                      + ("  [B&W]" if info["is_bw"] else ""))
            except Exception as e:
                print(f"  {f.name}: ERROR {e}", file=sys.stderr)
    out = args.root / OUT_NAME
    out.write_text(json.dumps(result))
    total = sum(v["shots_accepted"] for v in result.values())
    print(f"WROTE {out} - {total} accepted shots across {len(result)} files")


if __name__ == "__main__":
    main()
