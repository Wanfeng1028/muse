# Ported from browser-use/video-use (MIT License, Copyright (c) 2026 Browser Use)
# https://github.com/browser-use/video-use at 9575612f066aa517354790a645fd90f9f95a743b
# Source file: helpers/timeline_view.py. Adapted: numpy removed (one less dependency, and a
# system numpy built for the other CPU architecture will not import), so the waveform is
# ffmpeg PCM plus the stdlib array module and PIL only. Added cut markers (--mark), frame
# time labels, and no auto-resolved transcript path (pass --transcript explicitly).
"""Filmstrip + waveform + word labels PNG for one time range of a video.

N evenly spaced frames across [start, end], an RMS waveform ribbon under them with the
transcript's words labelled on it, gaps >= 400 ms shaded, and optional vertical cut
markers. A drill-down tool for decision points (an ambiguous pause, which of two takes,
a cut edge) and for the self check on a rendered cut. Not a scan tool.

Usage (python3 with Pillow):
    timeline_view.py <video> <start> <end> [-o out.png] [--n-frames 10]
                     [--transcript words.json] [--mark 12.34 --mark 15.0]
The transcript is any JSON with a Scribe-shaped "words" list: a source transcript from
transcribe.py, or cut_words.json from rough_cut.py for a rendered cut.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import subprocess
import sys
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageStat

BG = (18, 18, 22)
FG = (235, 235, 235)
DIM = (110, 110, 120)
CUT = (255, 70, 70)
SILENCE = (50, 80, 120, 120)
WAVE = (140, 180, 255)
FONT_CANDIDATES = ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Helvetica.ttc",
                   "/System/Library/Fonts/SFNSMono.ttf"]


def load_font(size: int) -> ImageFont.ImageFont:
    for fp in FONT_CANDIDATES:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except OSError:
                continue
    return ImageFont.load_default()


def extract_frames(video: Path, start: float, end: float, n: int, dest: Path) -> list[tuple[float, Path]]:
    n = max(1, n)
    times = [(start + end) / 2.0] if n == 1 else [start + i * (end - start) / (n - 1) for i in range(n)]
    # The last frame of a file has no frame after it: pull the final sample back one frame.
    times = [min(t, end - 0.05) for t in times]

    def grab(i_t: tuple[int, float]) -> tuple[float, Path]:
        i, t = i_t
        out = dest / f"f_{i:03d}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video),
                        "-frames:v", "1", "-q:v", "4", "-vf", "scale=320:-2", str(out)], check=True)
        return t, out

    with ThreadPoolExecutor(max_workers=4) as ex:
        return list(ex.map(grab, enumerate(times)))


def read_pcm(video: Path, start: float, end: float, rate: int = 16000) -> array.array:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(video),
                            "-t", f"{end - start:.3f}", "-map", "0:a:0", "-vn", "-ac", "1",
                            "-ar", str(rate), "-c:a", "pcm_s16le", str(wav)])
        if r.returncode != 0 or not wav.exists():
            return array.array("h")
        with wave.open(str(wav), "rb") as w:
            return array.array("h", w.readframes(w.getnframes()))


def envelope(pcm: array.array, samples: int) -> list[float]:
    """Windowed RMS, normalized to [0, 1] within the range."""
    if not pcm:
        return [0.0] * samples
    # exact bucket edges, so the ribbon spans [start, end] and lines up with the word bars
    # and cut markers (upstream's fixed window + truncation drew it ~22 ms late mid-range)
    env = []
    for k in range(samples):
        a, b = k * len(pcm) // samples, max(k * len(pcm) // samples + 1, (k + 1) * len(pcm) // samples)
        seg = pcm[a:min(b, len(pcm))]
        env.append(math.sqrt(sum(s * s for s in seg) / len(seg)) / 32768.0 if seg else 0.0)
    top = max(env) or 1.0
    return [v / top for v in env]


def words_in_range(transcript: Path | None, start: float, end: float) -> list[dict]:
    if not transcript or not transcript.exists():
        return []
    out = []
    for w in json.loads(transcript.read_text()).get("words", []):
        ws, we = w.get("start"), w.get("end")
        if ws is None or we is None or we <= start or ws >= end or w.get("type") == "spacing":
            continue
        out.append(w)
    return out


def find_silences(words: list[dict], start: float, end: float, threshold: float = 0.4) -> list[tuple[float, float]]:
    gaps, prev = [], start
    for w in words:
        ws = max(start, w["start"])
        if ws - prev >= threshold:
            gaps.append((prev, ws))
        prev = max(prev, w["end"])
    if end - prev >= threshold:
        gaps.append((prev, end))
    return gaps


def render_timeline(video: Path, start: float, end: float, out_path: Path, n_frames: int = 10,
                    transcript: Path | None = None, marks: list[float] | None = None,
                    title: str | None = None) -> dict:
    """Write the PNG. Returns per-frame mean luma so callers can flag black or flash frames."""
    marks = marks or []
    with tempfile.TemporaryDirectory() as tmp:
        frames = extract_frames(video, start, end, n_frames, Path(tmp))
        aspect = Image.open(frames[0][1]).width / Image.open(frames[0][1]).height
        # Fill a 1920 canvas: portrait phone frames get taller thumbnails instead of a
        # strip that covers half the width.
        frame_h = max(120, min(360, int((1820 - 4 * (len(frames) - 1)) / (len(frames) * aspect))))
        film_y = 50
        wave_y = film_y + frame_h + 40
        wave_h = 220
        label_y = wave_y + wave_h + 10
        imgs, lumas = [], []
        for t, fp in frames:
            img = Image.open(fp).convert("RGB")
            lumas.append(round(ImageStat.Stat(img.convert("L")).mean[0], 1))
            imgs.append((t, img.resize((max(1, int(frame_h * img.width / img.height)), frame_h), Image.LANCZOS)))

    total_w = sum(i.width for _, i in imgs) + (len(imgs) - 1) * 4
    canvas_w = max(1920, total_w + 100)
    canvas = Image.new("RGB", (canvas_w, label_y + 60), BG)
    draw = ImageDraw.Draw(canvas, "RGBA")
    f_head, f_label, f_small = load_font(22), load_font(14), load_font(12)
    head = title or video.name
    draw.text((50, 12), f"{head}   {start:.2f}s to {end:.2f}s   ({end - start:.2f}s, {len(imgs)} frames)",
              fill=FG, font=f_head)

    strip_w = canvas_w - 100
    scale = min(1.0, strip_w / max(1, total_w))
    cursor = 50
    for t, img in imgs:
        if scale < 1.0:
            img = img.resize((max(1, int(img.width * scale)), max(1, int(frame_h * scale))), Image.LANCZOS)
        canvas.paste(img, (cursor, film_y + (frame_h - img.height) // 2))
        draw.text((cursor + 2, film_y + frame_h + 4), f"{t:.2f}", fill=DIM, font=f_small)
        cursor += img.width + max(2, int(4 * scale))
    x0, x1 = 50, cursor
    span = max(1, x1 - x0)

    def tx(t: float) -> int:
        return int(x0 + (t - start) / max(1e-6, end - start) * span)

    draw.rectangle((x0, wave_y, x1, wave_y + wave_h), fill=(28, 28, 34))
    words = words_in_range(transcript, start, end)
    silences = find_silences(words, start, end) if words else []
    for a, b in silences:
        draw.rectangle((tx(a), wave_y, tx(b), wave_y + wave_h), fill=SILENCE)

    env = envelope(read_pcm(video, start, end), max(span, 200))
    mid, amp = wave_y + wave_h // 2, wave_h // 2 - 8
    top = [(x0 + int(i * span / max(1, len(env) - 1)), mid - int(v * amp)) for i, v in enumerate(env)]
    bot = [(x, 2 * mid - y) for x, y in top]
    if top:
        draw.polygon(top + bot[::-1], fill=(*WAVE, 60))
        draw.line(top, fill=WAVE, width=1)
        draw.line(bot, fill=WAVE, width=1)

    last_x = -9999
    for w in words:
        if w.get("type") != "word" or not (w.get("text") or "").strip():
            continue
        cx = (tx(w["start"]) + tx(w["end"])) // 2
        # word extent as a thin bar on the top edge of the waveform, so edges are readable
        draw.line((tx(w["start"]), wave_y + 1, tx(w["end"]), wave_y + 1), fill=FG, width=2)
        if cx - last_x < 28:
            continue
        draw.text((cx + 2, wave_y - 18), w["text"].strip(), fill=FG, font=f_small)
        last_x = cx

    for m in marks:
        if start <= m <= end:
            xm = tx(m)
            draw.line((xm, film_y - 6, xm, wave_y + wave_h + 4), fill=CUT, width=2)
            draw.text((xm + 3, wave_y + wave_h - 16), f"cut {m:.2f}", fill=CUT, font=f_small)

    ruler_y = wave_y + wave_h + 2
    for i in range(7):
        frac = i / 6
        xi = x0 + int(frac * span)
        draw.line((xi, ruler_y, xi, ruler_y + 6), fill=DIM, width=1)
        draw.text((xi - 20, ruler_y + 8), f"{start + frac * (end - start):.2f}s", fill=DIM, font=f_label)
    if silences:
        draw.text((x0, label_y + 30), f"shaded = gaps >= 400 ms between words ({len(silences)})",
                  fill=DIM, font=f_label)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG", optimize=True)
    return {"png": str(out_path), "frame_luma": lumas}


def main() -> None:
    ap = argparse.ArgumentParser(description="Filmstrip + waveform composite for a video range")
    ap.add_argument("video", type=Path)
    ap.add_argument("start", type=float)
    ap.add_argument("end", type=float)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--n-frames", type=int, default=10)
    ap.add_argument("--transcript", type=Path, default=None)
    ap.add_argument("--mark", type=float, action="append", default=[], help="Cut marker time (repeatable)")
    args = ap.parse_args()

    video = args.video.expanduser().resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")
    if args.end <= args.start:
        sys.exit("end must be > start")
    out = args.output or Path(tempfile.gettempdir()) / f"{video.stem}_{args.start:.2f}-{args.end:.2f}.png"
    res = render_timeline(video, args.start, args.end, out, args.n_frames, args.transcript, args.mark)
    print(f"saved: {res['png']}  frame luma {res['frame_luma']}")


if __name__ == "__main__":
    main()
