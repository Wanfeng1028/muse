#!/usr/bin/env python3
"""Key the green screen out of a take: presenter/fNNNNN.webp with alpha, numbered by edit frame.

  key_greenscreen.py <work> [--video take.mp4] [--mask x,y,w,h …] [--quality web|master]
                     [--workers N] [--max-height px] [--preview <t>] [--over '#0b1410']

Reads take.json from trim_take.py (without it, the whole video is the edit). Measures the screen from
sample frames instead of hand-set thresholds, and fails with the reason when the take can't be keyed.
Every source is converted to 30 fps edit frames; --max-height scales the take before keying, so a 4K
take needs no manual ffmpeg downscale.
With the optional vision setup (setup.sh --vision: opencv + the YuNet face model), the speaker's face is
measured across the take and recorded in take.json and faces.js, so presenter layouts frame an off-centre
speaker, and --preview also flags a burned-in banner near the frame's edges with a suggested --mask.
Resumable: a re-run keeps every complete frame and re-keys the rest, so a killed run just continues.
--preview <t> keys the one frame at edit time t and writes presenter-preview.png to judge the key first.
"""

import argparse
import concurrent.futures
import json
import math
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np

FPS = 30
CHUNK = 450  # largest job: small enough to spread across workers, large enough to amortise the seek
DEFAULT_MAX_HEIGHT = 1920 * 2  # composition height × 2, so the supersampled render keeps the source's detail
YUNET_MODEL = "face_detection_yunet_2023mar.onnx"  # opencv_zoo's YuNet face detector, fetched by setup.sh --vision


class TakeError(Exception):
    """A take that can't be keyed; carries the problem and the fix."""

    def __init__(self, problem, fix):
        super().__init__(problem)
        self.problem, self.fix = problem, fix


def frame_rate(text):
    num, _, den = text.partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,avg_frame_rate:format=duration", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True)
    info = json.loads(out.stdout)
    stream = info["streams"][0]
    declared, average = frame_rate(stream.get("r_frame_rate", "")), frame_rate(stream.get("avg_frame_rate", ""))
    # Phones record variable frame rate; the declared and average rates then disagree
    vfr = bool(declared and average and abs(declared - average) / max(declared, average) > 0.01)
    return stream["width"], stream["height"], float(info["format"]["duration"]), average or declared, vfr


def scaled_size(width, height, max_height):
    """Frame size to key at: the source size, or downscaled to --max-height (kept even for 4:2:0)."""
    if height <= max_height:
        return width, height
    limit = max(2, max_height - max_height % 2)
    return max(2, round(width * limit / height / 2) * 2), limit


def read_frame(video, seconds, width, height, vf):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{seconds:.6f}", "-i", str(video),
                          "-vf", vf, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(height, width, 3)


def dominance(frame):
    rgb = frame.astype(np.int16)
    return rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2])


def measure(video, take, width, height, vf):
    """Screen colour and matte thresholds from the frame borders, where the screen shows round the speaker."""
    samples = [take["in"] + take["duration"] * k / 9 for k in range(1, 9)]
    borders, colours = [], []
    bw, bh = max(8, width // 10), max(8, height // 10)
    for seconds in samples:
        frame = read_frame(video, seconds, width, height, vf)
        regions = [frame[:, :bw], frame[:, -bw:], frame[:bh, bw:-bw]]
        for region in regions:
            d = dominance(region).ravel()
            borders.append(d)
            green = region.reshape(-1, 3)[d > 8]
            if len(green):
                colours.append(green)
    border = np.concatenate(borders)
    screen_share = float((border > 8).mean())
    if screen_share < 0.5:
        raise TakeError(f"Less than half of the frame border is green screen ({screen_share:.0%}); this take has no screen to key",
                        "edit it with face shots instead (extract_face.sh), or reframe the recording")
    screen = border[border > 8]
    floor = float(np.percentile(screen, 2))
    if floor < 10:
        raise TakeError(f"The screen is too dim or uneven to key (its greenest 98% only clears the subject by {floor:.0f})",
                        "light the screen evenly and separately from the speaker; see docs/recording-guide.md")
    # The matte ramps from opaque at `low` to clear at `high`, kept below the screen's weakest green
    high = round(floor * 0.75)
    low = max(2, round(high * 0.2))
    pixels = np.concatenate(colours).astype(np.float32)
    colour = np.median(pixels, axis=0).round().astype(int).tolist()
    # Green clothing, logos and spill-tinted fabric are green but not the screen's green: measure how tight
    # the screen's own colour is, so only pixels near it can turn transparent
    r, g = chromaticity(pixels)
    centre = (float(np.median(r)), float(np.median(g)))
    spread = float(np.percentile(np.hypot(r - centre[0], g - centre[1]), 99))
    return {"screen": colour, "low": low, "high": high, "margin": round(floor, 1), "borderGreen": round(screen_share, 2),
            "centre": centre, "near": spread * 1.2, "far": spread * 1.2 + max(0.02, spread)}


def chromaticity(rgb):
    """Colour with brightness divided out, so a screen in shadow and in light reads the same."""
    total = rgb.sum(axis=-1, dtype=np.float32) + 1e-6
    return rgb[..., 0] / total, rgb[..., 1] / total


def vision_model():
    """The YuNet model setup.sh --vision recorded in config.json (or left in the default cache); None if absent."""
    config = Path(os.environ.get("VV_CONFIG") or
                  Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "shenghua" / "config.json")
    model = None
    try:
        model = json.loads(config.read_text(encoding="utf-8")).get("vision", {}).get("model")
    except (OSError, json.JSONDecodeError):
        pass
    if not model:
        model = Path(os.environ.get("VV_YUNET_DIR") or Path.home() / ".cache" / "shenghua" / "yunet") / YUNET_MODEL
    model = Path(model).expanduser()
    return model if model.is_file() else None


def load_detector():
    """The optional YuNet face detector (setup.sh --vision); None when it isn't installed, so every step works as before."""
    model = vision_model()
    if model is None:
        return None
    try:
        import cv2
    except ImportError:
        return None
    try:
        return cv2.FaceDetectorYN.create(str(model), "", (320, 320))
    except cv2.error:
        return None


def face_in_image(detector, rgb):
    """The largest face in an RGB image, as [centre-x, centre-y, w, h] fractions of the frame; None if no face."""
    import cv2  # the caller holds a detector, so setup.sh --vision installed opencv
    height, width = rgb.shape[:2]
    # Detection runs at ~640px: faces in a take or portrait are far larger, and the small pass is fast on CPU
    scale = min(1.0, 640 / max(height, width))
    small = rgb if scale == 1 else cv2.resize(rgb, (round(width * scale), round(height * scale)))
    detector.setInputSize((small.shape[1], small.shape[0]))
    _, faces = detector.detect(np.ascontiguousarray(small[..., ::-1]))  # YuNet expects BGR
    if faces is None or len(faces) == 0:
        return None
    x, y, w, h = (float(v) for v in max(faces, key=lambda f: f[2] * f[3])[:4])
    return [round((x + w / 2) / small.shape[1], 4), round((y + h / 2) / small.shape[0], 4),
            round(w / small.shape[1], 4), round(h / small.shape[0], 4)]


def measure_face(video, take, width, height, vf, detector):
    """Median box of the take's largest face over sampled frames, as fractions; None when no face is seen."""
    samples = [take["in"] + take["duration"] * k / 8 for k in range(1, 8)]
    boxes = [box for seconds in samples
             if (box := face_in_image(detector, read_frame(video, seconds, width, height, vf)))]
    if len(boxes) < 3:  # a face in a frame or two is a poster on the wall, not the speaker
        return None
    return [float(np.median([box[i] for box in boxes])) for i in range(4)]


def read_faces(work):
    path = work / "faces.js"
    if path.is_file():
        match = re.fullmatch(r"window\.FACES\s*=\s*(\{.*\})\s*;?\s*", path.read_text(encoding="utf-8"), re.S)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    return {}


def record_face(work, key, centre):
    """Merge one face position into the work dir's faces.js, which the composition reads for object-position."""
    faces = read_faces(work)
    faces[key] = [round(float(c), 4) for c in centre]
    (work / "faces.js").write_text(f"window.FACES={json.dumps(faces)};\n", encoding="utf-8")


def find_banner(frame, matte):
    """A burned-in text banner (a name tag) near the frame's top or bottom edge, as x,y,w,h in frame pixels.

    Edge and contrast analysis only, no OCR: a banner is a wide, flat, uniformly coloured rectangle that is not
    the screen, and whose colour differs from whatever surrounds it — a plain shirt is just as flat and wide,
    but merges into its surround, which is how it is rejected.
    """
    step = max(1, frame.shape[0] // 360)
    small = frame[::step, ::step].astype(np.float32)
    height, width = small.shape[:2]
    gray = small.mean(axis=-1)
    rgb = small.astype(np.int16)
    # Only pixels that key as subject can be burned in; the screen is the frame's other flat expanse
    subject = (rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2])) < matte["low"]
    mean = box_mean(gray, 5)
    flat = np.sqrt(np.maximum(box_mean(gray * gray, 5) - mean * mean, 0)) < 16
    # Label connected flat-subject regions on a coarse grid, so a banner overlapping the speaker in rows
    # still comes out as its own region; the 90×160 grid keeps the flood fill trivial
    BLOCK = 4
    gh, gw = height // BLOCK, width // BLOCK
    grid = (subject & flat)[:gh * BLOCK, :gw * BLOCK].reshape(gh, BLOCK, gw, BLOCK).mean((1, 3)) > 0.5
    bands = np.zeros_like(grid)
    bands[int(gh * 0.70):] = True
    bands[:int(gh * 0.12)] = True
    grid &= bands
    seen, best = np.zeros_like(grid), None
    for start in zip(*np.nonzero(grid & ~seen)):
        if seen[start]:
            continue
        cells, queue = [], deque([start])
        seen[start] = True
        while queue:
            cy, cx = queue.popleft()
            cells.append((cy, cx))
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < gh and 0 <= nx < gw and grid[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        ys, xs = [c[0] for c in cells], [c[1] for c in cells]
        y0, y1, x0, x1 = min(ys) * BLOCK, (max(ys) + 1) * BLOCK, min(xs) * BLOCK, (max(xs) + 1) * BLOCK
        w, h = x1 - x0, y1 - y0
        if w < 0.12 * width or h < 5 or w / h < 2.2 or h > 0.15 * height:
            continue
        # The surround is read from a ring 6–12 px out: the component box sits a few px inside the banner's
        # true edge (the boundary cells fail the flatness test), so a ring hugging the box reads banner pixels
        pad = 6
        outer = np.zeros((height, width), bool)
        outer[max(0, y0 - 2 * pad):y1 + 2 * pad, max(0, x0 - 2 * pad):x1 + 2 * pad] = True
        inner = np.zeros((height, width), bool)
        inner[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] = True
        ring = outer & ~inner
        ring_subject = ring & subject
        if ring_subject.sum() >= 200:
            surround = np.median(small[ring_subject], axis=0)
        else:
            surround = np.array(matte["screen"], np.float32)  # the banner hangs over the screen, not the speaker
        if np.linalg.norm(np.median(small[y0:y1, x0:x1].reshape(-1, 3), axis=0) - surround) < 30:
            continue
        if best is None or w * h > best[2] * best[3]:
            best = (x0, y0, w, h)
    if best is None:
        return None
    return [best[0] * step, best[1] * step, best[2] * step, best[3] * step]


def box_mean(plane, radius):
    """Mean over a (2r+1)² square at every pixel, from an integral image so the window size costs nothing."""
    height, width = plane.shape
    padded = np.pad(plane, ((radius + 1, radius), (radius + 1, radius)), mode="edge").astype(np.float64)
    integral = padded.cumsum(0).cumsum(1)
    size = 2 * radius + 1
    total = integral[size:size + height, size:size + width] - integral[:height, size:size + width] \
        - integral[size:size + height, :width] + integral[:height, :width]
    return (total / (size * size)).astype(np.float32)


def neighbourhood(plane, combine):
    height, width = plane.shape
    padded = np.pad(plane, 1, mode="edge")
    result = padded[1:-1, 1:-1].copy()
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            if (dy, dx) != (1, 1):
                result = combine(result, padded[dy:dy + height, dx:dx + width])
    return result


def box5(plane):
    return neighbourhood(neighbourhood(plane, np.add), np.add)


def key(frame, matte):
    rgb = frame.astype(np.int16)
    difference = rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2])
    alpha = np.clip((matte["high"] - difference) / (matte["high"] - matte["low"]), 0, 1).astype(np.float32)
    r, g = chromaticity(rgb)
    distance = np.hypot(r - matte["centre"][0], g - matte["centre"][1])
    # A green logo or spill-tinted fabric is a hole inside the speaker, not the screen: fill pixels far from the
    # screen's colour, but only where no real screen shows nearby, so the outline's blend of skin and screen
    # still keys away instead of leaving a rim
    unlike_screen = np.clip((distance - matte["near"]) / (matte["far"] - matte["near"]), 0, 1)
    screen_nearby = box_mean((distance < matte["near"]).astype(np.float32), 25)
    enclosed = np.clip((0.15 - screen_nearby) / 0.1, 0, 1)
    alpha = np.maximum(alpha, unlike_screen * enclosed)
    alpha[alpha < 0.04] = 0
    for x, y, w, h in matte["masks"]:
        alpha[y:y + h, x:x + w] = 0
    # Compression smears screen colour 1-2px into the subject, so choke the matte past it, then soften
    solid = alpha
    for _ in range(2):
        solid = neighbourhood(solid, np.minimum)
    alpha = np.minimum(alpha, neighbourhood(solid, np.add) / 9)
    core = (solid >= 0.999).astype(np.float32)
    weight = box5(core)
    edge = (alpha < 1) & (weight > 0)
    # Spill reaches a few px into the subject and raises red with green, so a dim screen leaves a yellow-green
    # rim the clamp below can't see. Round the matte edge, subtract the colour each pixel has along the screen's
    # chromaticity direction beyond the subject's own (read from deep core, which the spill hasn't reached), in
    # proportion to how far its chromaticity has slid toward the screen's. Work only on the core's bounding box:
    # the band limit keeps logos and garments untouched, and the background costs nothing
    if core.any():
        pad = 14  # the 4px band plus the 9px window the deep-core estimate averages over
        ys, xs = np.nonzero(core)
        y0, y1 = max(0, ys.min() - pad), min(rgb.shape[0], ys.max() + pad + 1)
        x0, x1 = max(0, xs.min() - pad), min(rgb.shape[1], xs.max() + pad + 1)
        sub = rgb[y0:y1, x0:x1]
        deep = core[y0:y1, x0:x1]
        for _ in range(4):
            deep = neighbourhood(deep, np.minimum)
        if deep.any():
            near = box_mean(deep, 9)
            band = (box_mean(core[y0:y1, x0:x1], 4) > 0) & (alpha[y0:y1, x0:x1] > 0) & (near > 0)
            if band.any():
                subject = np.stack([box_mean(sub[..., c].astype(np.float32) * deep, 9) / np.maximum(near, 1e-6)
                                    for c in range(3)], axis=-1)
                qr, qg = chromaticity(sub)
                er, eg = chromaticity(subject)
                dr, dg = matte["centre"][0] - er, matte["centre"][1] - eg
                slide = dr * dr + dg * dg
                # Share of the pixel's light that sits on the path from the subject's colour to the screen's:
                # ramps 0→1 over the first quarter of the way, so natural colour variation is left alone
                slid = ((qr - er) * dr + (qg - eg) * dg) / np.maximum(slide, 1e-9)
                screenness = np.clip((slid - 0.02) / 0.2, 0, 1)
                # A subject the screen's own colour gives no slide direction, so it is left alone, not guessed at
                screenness[slide < 1e-3] = 0
                direction = np.array(matte["screen"], np.float32)
                direction /= np.linalg.norm(direction)
                excess = np.maximum(0, ((sub - subject) * direction).sum(-1)) * screenness
                valid = band & (excess > 0)
                sub[valid] = np.clip(sub[valid] - excess[valid, None] * direction, 0, 255).round().astype(np.int16)
    # Edge pixels are part screen; give them the subject's own colour from the solid core next to them,
    # which also keeps 4:2:0 chroma from averaging screen green into the edge
    for channel in range(3):
        extended = box5(rgb[..., channel] * core)
        rgb[..., channel][edge] = (extended[edge] / weight[edge]).astype(np.int16)
    # Green light bounced onto skin reads as a cast once the screen is gone; only colours near the screen's
    # are spill, so a green logo or garment keeps its own green
    spill = distance < matte["far"]
    rgb[..., 1][spill] = np.minimum(rgb[..., 1], np.maximum(rgb[..., 0], rgb[..., 2]) + 4)[spill]
    out = np.empty(frame.shape[:2] + (4,), np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255)
    out[..., 3] = (alpha * 255).astype(np.uint8)
    return out


def complete(path):
    """A WebP is whole when its RIFF header's size matches the file; a killed writer leaves it short."""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            header = handle.read(12)
    except OSError:
        return False
    return len(header) == 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP" and \
        int.from_bytes(header[4:8], "little") + 8 == size


def encoder_args(quality):
    if quality == "master":
        return ["-c:v", "libwebp", "-lossless", "1", "-compression_level", "4", "-pix_fmt", "bgra"]
    return ["-c:v", "libwebp", "-quality", "94", "-compression_level", "4", "-pix_fmt", "yuva420p"]


def has_webp_encoder():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
    return "libwebp" in out.stdout


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def key_run(video, out_dir, first_edit, count, take, matte, width, height, vf, quality, parent):
    """Key `count` edit frames starting at `first_edit`; returns how many were written."""
    start = (take["firstFrame"] + first_edit) / FPS
    reader = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{start:.6f}", "-i", str(video), "-an",
                               "-vf", vf, "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                              stdout=subprocess.PIPE)
    writer = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                               "-s", f"{width}x{height}", "-r", str(FPS), "-i", "-", *encoder_args(quality),
                               "-start_number", str(first_edit), str(out_dir / "f%05d.webp")], stdin=subprocess.PIPE)
    size, written = width * height * 3, 0
    while written < count:
        # A killed run must not leave workers writing frames a resumed run is also writing. Ask whether the
        # main process lives rather than comparing parent ids: under forkserver or spawn the parent is a helper
        if not alive(parent):
            reader.terminate()
            break
        raw = reader.stdout.read(size)
        if len(raw) < size:
            break
        writer.stdin.write(key(np.frombuffer(raw, np.uint8).reshape(height, width, 3), matte).tobytes())
        written += 1
    writer.stdin.close()
    writer.wait()
    reader.wait()
    return written


def runs(missing, workers):
    """Contiguous runs of missing frames, split so every worker gets a share of a short take too."""
    size = max(30, min(CHUNK, math.ceil(len(missing) / workers)))
    jobs, start, previous = [], None, None
    for frame in missing:
        if start is None or frame != previous + 1 or frame - start >= size:
            if start is not None:
                jobs.append((start, previous - start + 1))
            start = frame
        previous = frame
    if start is not None:
        jobs.append((start, previous - start + 1))
    return jobs


def parse_mask(text):
    try:
        x, y, w, h = (int(v) for v in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"--mask takes x,y,w,h in source pixels, got {text!r}")
    return x, y, w, h


def main() -> int:
    parser = argparse.ArgumentParser(description="Key a green-screen take into transparent presenter frames.")
    parser.add_argument("work", type=Path)
    parser.add_argument("--video", type=Path, help="the take (default: the source recorded in take.json)")
    parser.add_argument("--mask", type=parse_mask, action="append", default=[],
                        help="x,y,w,h in source pixels to make transparent, e.g. a burned-in name banner (repeatable)")
    parser.add_argument("--quality", choices=["web", "master"], default="web",
                        help="web: 4:2:0 lossy WebP (~70 KB/frame) · master: lossless full colour (~10x larger)")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    parser.add_argument("--max-height", type=int, default=DEFAULT_MAX_HEIGHT,
                        help=f"scale the take to at most this height before keying, so a 4K take needs no manual "
                             f"ffmpeg downscale (default: {DEFAULT_MAX_HEIGHT} = composition height × 2)")
    parser.add_argument("--preview", type=float, help="key only the frame at this edit time and write presenter-preview.png")
    parser.add_argument("--over", default="#0b1410", help="background colour for --preview")
    args = parser.parse_args()

    take_path = args.work / "take.json"
    take = json.loads(take_path.read_text(encoding="utf-8")) if take_path.exists() else None
    video = args.video or (Path(take["source"]) if take else None)
    if video is None or not video.is_file():
        print(f"No take to key: {video or 'pass --video, or run trim_take.py first'}", file=sys.stderr)
        print("Next: pass --video <the to-camera recording>", file=sys.stderr)
        return 1
    # A minimal ffmpeg (Homebrew's core formula dropped libwebp) can't write WebP; the writer dies mid-run
    if not has_webp_encoder():
        print("This ffmpeg has no libwebp encoder, so presenter frames can't be written", file=sys.stderr)
        print("Next: install an ffmpeg with webp (macOS: brew install ffmpeg-full · "
              "Debian/Ubuntu: apt install ffmpeg)", file=sys.stderr)
        return 1
    # The composition always loads faces.js (window.FACES); without the file a render fails on the missing request
    args.work.mkdir(parents=True, exist_ok=True)
    if not (args.work / "faces.js").exists():
        (args.work / "faces.js").write_text("window.FACES={};\n", encoding="utf-8")
    width, height, length, fps, vfr = probe(video)
    if take is None:
        take = {"in": 0.0, "duration": length, "firstFrame": 0}
    frames = math.ceil(take["duration"] * FPS)
    kw, kh = scaled_size(width, height, args.max_height)
    # fps first, so a 60 fps source is halved before the scaler touches it; both make edit frame N the moment
    # N/30 s, whatever rate the recording is
    vf = f"fps={FPS}" + (f",scale={kw}:{kh}" if (kw, kh) != (width, height) else "")
    source = f"source {width}×{height}"
    if fps:
        source += f" · {fps:.4g} fps{' variable' if vfr else ''}"
        if vfr or abs(fps - FPS) > 0.01:
            source += f" → converted to {FPS} fps"
    if (kw, kh) != (width, height):
        source += f" · keyed at {kw}×{kh} (--max-height {args.max_height})"
    print(source, flush=True)

    try:
        matte = measure(video, take, kw, kh, vf)
    except TakeError as error:
        print(error.problem, file=sys.stderr)
        print(f"Next: {error.fix}", file=sys.stderr)
        return 1
    # Masks are given in source pixels, so scale them with the take
    matte["masks"] = [(round(x * kw / width), round(y * kh / height),
                       max(1, round(w * kw / width)), max(1, round(h * kh / height))) for x, y, w, h in args.mask]
    print(f"screen rgb{tuple(matte['screen'])} · margin {matte['margin']} · matte {matte['low']}–{matte['high']} · "
          f"{len(args.mask)} mask(s)", flush=True)

    detector = load_detector()
    face = measure_face(video, take, kw, kh, vf, detector) if detector else None
    if face:
        take["face"] = dict(zip("xywh", (round(v, 4) for v in face)))
        if take_path.exists():
            take_path.write_text(json.dumps(take, indent=2) + "\n", encoding="utf-8")
        record_face(args.work, "presenter", face[:2])
        print(f"speaker face at {face[0]:.0%}×{face[1]:.0%} of the frame (median over the take) → take.json + faces.js",
              flush=True)
    elif detector:
        print("no face found in the sampled frames; presenter layouts assume a centred speaker", flush=True)

    if args.preview is not None:
        frame = read_frame(video, take["in"] + args.preview, kw, kh, vf)
        keyed = key(frame, matte).astype(np.float32)
        over = np.array([int(args.over[i:i + 2], 16) for i in (1, 3, 5)], np.float32)
        a = keyed[..., 3:4] / 255
        composite = (keyed[..., :3] * a + over * (1 - a)).round().astype(np.uint8)
        target = args.work / "presenter-preview.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{kw}x{kh}",
                        "-i", "-", "-frames:v", "1", "-update", "1", str(target)], input=composite.tobytes(), check=True)
        print(f"preview → {target}")
        if detector:
            banner = find_banner(frame, matte)
            if banner:
                # Masks are passed in source pixels; pad a little so the banner's anti-aliased edge goes too
                pad_x, pad_y = round(0.01 * width), round(0.02 * height)
                mx = max(0, round(banner[0] * width / kw) - pad_x)
                my = max(0, round(banner[1] * height / kh) - pad_y)
                mw = min(width - mx, round(banner[2] * width / kw) + 2 * pad_x)
                mh = min(height - my, round(banner[3] * height / kh) + 2 * pad_y)
                print(f"possible burned-in banner near the frame edge; if the preview shows one, hide it with: "
                      f"--mask {mx},{my},{mw},{mh}")
        print("Next: look at it (hair, glasses, shoulders, any banner); fix with --mask, then run without --preview")
        return 0

    out_dir = args.work / "presenter"
    out_dir.mkdir(parents=True, exist_ok=True)
    missing = [n for n in range(frames) if not complete(out_dir / f"f{n:05d}.webp")]
    if not missing:
        print(f"{frames}/{frames} presenter frames already keyed → {out_dir}")
        print("Next: author the composition with presenter(); see the Presenter blocks in scene-blocks.md")
        return 0
    jobs = runs(missing, args.workers)
    print(f"keying {len(missing)} of {frames} frames ({frames - len(missing)} already done) · {len(jobs)} jobs · "
          f"{args.workers} workers", flush=True)
    started, done = time.time(), 0
    # spawn on every platform and Python version, so workers behave the same on Linux, macOS and CI
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [pool.submit(key_run, video, out_dir, first, count, take, matte, kw, kh, vf, args.quality, os.getpid())
                   for first, count in jobs]
        for future in concurrent.futures.as_completed(futures):
            done += future.result()
            rate = done / max(1e-6, time.time() - started)
            print(f"  {done}/{len(missing)} keyed · {rate:.1f} fps · ~{(len(missing) - done) / max(rate, 1e-6) / 60:.0f} min left",
                  flush=True)
    left = [n for n in range(frames) if not complete(out_dir / f"f{n:05d}.webp")]
    # Audio often outlasts the video stream by a fraction of a frame, so the edit's last frame or two have no
    # source frame; the speaker holds their last frame rather than vanishing for 1/30 s
    if left and len(left) <= 2 and left == list(range(frames - len(left), frames)) and left[0] > 0:
        for n in left:
            shutil.copy2(out_dir / f"f{left[0] - 1:05d}.webp", out_dir / f"f{n:05d}.webp")
        print(f"held the last video frame for {len(left)} frame(s) past the end of the video stream")
        left = []
    if left:
        print(f"{len(left)} frames still missing (first: {left[0]})", file=sys.stderr)
        print("Next: re-run the same command; it keys only what is missing", file=sys.stderr)
        return 1
    print(f"{frames}/{frames} presenter frames → {out_dir} · {(time.time() - started) / 60:.1f} min")
    print("Next: author the composition with presenter(); see the Presenter blocks in scene-blocks.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
