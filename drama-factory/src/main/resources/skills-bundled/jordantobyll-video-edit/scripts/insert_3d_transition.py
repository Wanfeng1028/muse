#!/usr/bin/env python3
"""Splice a short 3D "swivel" teaser into the opening of a video.

The teaser is a sped-up preview of a later portion of the same video,
rendered with a rotating 3D effect (via Remotion). The original audio is
kept playing continuously underneath so the cut never feels like a pause.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Encoding preferences -------------------------------------------------------
HW_ENCODER = "hevc_videotoolbox"
SW_ENCODER = "libx265"
HW_BITRATE = "17M"
SW_CRF = "18"
OUTPUT_FPS = 30

_hw_available = None

DEFAULT_INSERT_AT = 3.0
DEFAULT_DURATION = 5.0
DEFAULT_TEASER_START = 60.0
SPEED_CAP = 100.0

EFFECTS_PROJECT = Path(__file__).parent / "video_effects"


def _probe_hardware_encoder():
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return HW_ENCODER in proc.stdout
    except Exception:
        return False


def _encoder_flags():
    global _hw_available
    if _hw_available is None:
        _hw_available = _probe_hardware_encoder()
        print("🚀 hardware HEVC" if _hw_available else "💻 software HEVC (libx265)")
    if _hw_available:
        return [
            "-c:v", HW_ENCODER,
            "-b:v", HW_BITRATE,
            "-r", str(OUTPUT_FPS),
            "-tag:v", "hvc1",
        ]
    return [
        "-c:v", SW_ENCODER,
        "-preset", "fast",
        "-crf", SW_CRF,
        "-r", str(OUTPUT_FPS),
        "-tag:v", "hvc1",
    ]


def _probe_video(path):
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration",
            "-show_entries", "format=duration",
            "-of", "json",
            path,
        ],
        capture_output=True,
        text=True,
    )
    data = json.loads(proc.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format", {})

    fps_raw = stream.get("r_frame_rate", "30/1")
    if "/" in fps_raw:
        num, den = fps_raw.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_raw)

    duration = float(stream.get("duration") or fmt.get("duration", 0))

    return {
        "width": int(stream.get("width", 1920)),
        "height": int(stream.get("height", 1080)),
        "fps": fps,
        "duration": duration,
    }


def _extract_teaser_frames(input_path, start_s, source_dur, out_dur,
                           frames_dir, width, height):
    """Pull the frames the Remotion composition will render."""
    REMOTION_FPS = 60
    n_frames = int(out_dur * REMOTION_FPS)
    interval = source_dur / n_frames

    # Fresh frames directory
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("frame_*.jpg"):
        old.unlink()

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", input_path,
            "-ss", str(start_s),
            "-vf", f"fps={1/interval}",
            "-vframes", str(n_frames),
            "-q:v", "2",
            "-loglevel", "error",
            str(frames_dir / "frame_%04d.jpg"),
        ],
        check=True,
    )
    return n_frames


def _make_background(frames_dir, bg_image, bg_color, width, height):
    dest = frames_dir / "bg_image.png"
    if bg_image and os.path.exists(bg_image):
        shutil.copy(bg_image, dest)
    else:
        color = bg_color.replace("#", "0x")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c={color}:s={width}x{height}:d=1",
                "-vframes", "1",
                "-loglevel", "error",
                str(dest),
            ],
            check=True,
        )


def _render_teaser(input_path, output_path, start_s, source_dur,
                   out_dur, playback_rate, bg_color, bg_image):
    info = _probe_video(input_path)
    print(f"📹 source: {info['width']}x{info['height']} @ {info['fps']:.2f}fps")

    frames_dir = EFFECTS_PROJECT / "public" / "frames"
    n_frames = _extract_teaser_frames(
        input_path, start_s, source_dur, out_dur,
        frames_dir, info["width"], info["height"],
    )
    print(f"📸 extracted {n_frames} frames")

    _make_background(
        frames_dir, bg_image, bg_color, info["width"], info["height"]
    )

    print("🎬 rendering Pan3D teaser via Remotion")
    subprocess.run(
        [
            "npx", "remotion", "render",
            "src/dynamic-index.ts", "Pan3D",
            output_path,
            "--props", json.dumps({
                "frameCount": n_frames,
                "playbackRate": playback_rate,
            }),
            "--concurrency", "4",
            "--log", "error",
        ],
        cwd=EFFECTS_PROJECT,
        check=True,
    )
    print(f"✅ teaser rendered → {output_path}")


def _composite(input_path, output_path, insert_at, duration, teaser_start,
               bg_color, bg_image):
    info = _probe_video(input_path)
    total_dur = info["duration"]

    if teaser_start >= total_dur:
        raise ValueError(
            f"--teaser-start ({teaser_start}s) exceeds video duration ({total_dur}s)"
        )

    available = total_dur - teaser_start
    uncapped_rate = available / duration
    if uncapped_rate > SPEED_CAP:
        rate = SPEED_CAP
        teaser_content = duration * SPEED_CAP
        print(f"   capping playback at {SPEED_CAP}x (requested {uncapped_rate:.1f}x)")
    else:
        rate = uncapped_rate
        teaser_content = available

    print("🎬 Insert 3D swivel teaser")
    print(f"   input     : {input_path}")
    print(f"   insert at : {insert_at}s")
    print(f"   duration  : {duration}s")
    print(f"   source    : {teaser_start}s → {total_dur:.1f}s "
          f"({teaser_content:.1f}s at {rate:.1f}x)")

    if insert_at + duration > total_dur:
        raise ValueError(
            f"insert point + duration ({insert_at + duration}s) "
            f"exceeds video duration ({total_dur}s)"
        )

    with tempfile.TemporaryDirectory() as tmp:
        teaser_path = os.path.join(tmp, "teaser.mp4")
        _render_teaser(
            input_path, teaser_path,
            start_s=teaser_start,
            source_dur=teaser_content,
            out_dur=duration,
            playback_rate=rate,
            bg_color=bg_color,
            bg_image=bg_image,
        )

        enc = _encoder_flags()

        # Split into head / teaser / tail (video only — audio comes later)
        head = os.path.join(tmp, "head.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-t", str(insert_at), "-an"]
            + enc + ["-loglevel", "error", head],
            check=True,
        )

        mid = os.path.join(tmp, "mid.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", teaser_path, "-an"]
            + enc + ["-loglevel", "error", mid],
            check=True,
        )

        tail = os.path.join(tmp, "tail.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path,
             "-ss", str(insert_at + duration), "-an"]
            + enc + ["-loglevel", "error", tail],
            check=True,
        )

        concat_list = os.path.join(tmp, "concat.txt")
        with open(concat_list, "w") as fh:
            for p in (head, mid, tail):
                fh.write(f"file '{p}'\n")

        stitched = os.path.join(tmp, "stitched.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_list, "-c", "copy",
             "-loglevel", "error", stitched],
            check=True,
        )

        audio = os.path.join(tmp, "audio.aac")
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-vn",
             "-c:a", "aac", "-b:a", "192k",
             "-loglevel", "error", audio],
            check=True,
        )

        subprocess.run(
            ["ffmpeg", "-y",
             "-i", stitched, "-i", audio,
             "-c:v", "copy", "-c:a", "copy",
             "-shortest",
             "-loglevel", "error",
             output_path],
            check=True,
        )

    print(f"\n✅ wrote {output_path}")
    print(f"   timeline: [0–{insert_at}s] [teaser {duration}s] "
          f"[{insert_at + duration}s–end]")
    print("   audio   : original preserved throughout")


def main():
    ap = argparse.ArgumentParser(
        description="Insert a 3D swivel teaser into a video"
    )
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--insert-at", type=float, default=DEFAULT_INSERT_AT)
    ap.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    ap.add_argument("--teaser-start", type=float, default=DEFAULT_TEASER_START)
    ap.add_argument("--bg-color", type=str, default="#2d3436")
    ap.add_argument("--bg-image", type=str, default=None)
    args = ap.parse_args()

    _composite(
        input_path=args.input,
        output_path=args.output,
        insert_at=args.insert_at,
        duration=args.duration,
        teaser_start=args.teaser_start,
        bg_color=args.bg_color,
        bg_image=args.bg_image,
    )


if __name__ == "__main__":
    main()
