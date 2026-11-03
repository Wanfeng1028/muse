#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.1"]
# ///
"""Simulate how a poster frame looks as a chat thumbnail (WhatsApp, Slack, X, Discord show frame 0 of the video).

Inputs: poster images and/or videos (frame 0 is taken), and/or Remotion <Still> ids rendered with --render.
Each becomes a ~300 px thumbnail with a play button and a duration badge; verticals also get a 4:5 centre crop
(many chat apps crop tall videos). Light and dark chat backgrounds, one sheet.
Output: out/review/poster-chat.png (and out/review/<Still>.png for --render).
--burn POSTER writes a copy of the (single) input video with POSTER on frame 0 only (re-encodes video, copies audio).
Examples:
  poster_check.py out/final/film-16x9.mp4 out/final/film-9x16.mp4
  poster_check.py --render PosterWide,PosterTall --duration 1:13
  poster_check.py out/final/film-16x9.mp4 --burn out/review/PosterWide.png --burn-out out/final/film-16x9-poster.mp4
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
BACKGROUNDS = {"light": (239, 234, 226), "dark": (11, 20, 26)}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="*", type=Path, help="poster images or videos")
    parser.add_argument("--render", help="Remotion <Still> ids to render first, comma separated")
    parser.add_argument("--entry", help="Remotion entry point (default: project config)")
    parser.add_argument("--props", help="input props JSON for --render")
    parser.add_argument("--duration", help="badge text, e.g. 1:13 (default: from the first video input)")
    parser.add_argument("--width", type=int, default=300, help="thumbnail width for landscape (default 300)")
    parser.add_argument("--out", type=Path, default=Path("out/review/poster-chat.png"))
    parser.add_argument("--burn", type=Path, help="poster image to put on frame 0 of the single input video")
    parser.add_argument("--burn-out", type=Path, help="output MP4 for --burn (default: <video>-poster.mp4 in out/final/)")
    parser.add_argument("--crf", type=int, default=16, help="x264 CRF for --burn (default 16)")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def resolve_binary(name: str, verbose: bool) -> str:
    candidate = os.environ.get(name.upper()) or shutil.which(name)
    if not candidate:
        sys.exit(f"{name} not found: set ${name.upper()} or install ffmpeg (brew install ffmpeg / apt install ffmpeg)")
    if verbose:
        print(f"using {name}: {candidate}", file=sys.stderr)
    return candidate


def run(command: list[str], verbose: bool) -> None:
    if verbose:
        print("$", " ".join(command), file=sys.stderr)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"command failed: {' '.join(command[:4])} ...\n{result.stderr[-1500:]}")


def render_stills(arguments: argparse.Namespace, review_dir: Path) -> list[Path]:
    paths = []
    for still_id in (value.strip() for value in arguments.render.split(",") if value.strip()):
        target = review_dir / f"{still_id}.png"
        command = ["npx", "remotion", "still"] + ([arguments.entry] if arguments.entry else [])
        command += [still_id, str(target), "--log=error"] + ([f"--props={arguments.props}"] if arguments.props else [])
        run(command, arguments.verbose)
        print(f"wrote {target}")
        paths.append(target)
    return paths


def video_duration(ffprobe: str, video: Path) -> float:
    output = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                            capture_output=True, text=True, check=True).stdout
    return float(output.strip())


def first_frame(ffmpeg: str, video: Path, folder: Path, verbose: bool) -> Path:
    target = folder / f"{video.stem}-frame0.png"
    run([ffmpeg, "-v", "error", "-y", "-i", str(video), "-frames:v", "1", "-update", "1", str(target)], verbose)
    return target


def format_duration(seconds: float) -> str:
    whole = round(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def center_crop(image: Image.Image, ratio: float) -> Image.Image:
    height = int(image.width / ratio)
    top = (image.height - height) // 2
    return image.crop((0, top, image.width, top + height))


def chat_thumbnail(image: Image.Image, width: int, badge: str | None) -> Image.Image:
    thumbnail = image.convert("RGB").resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    draw = ImageDraw.Draw(thumbnail, "RGBA")
    radius = int(width * 0.09)
    cx, cy = thumbnail.width // 2, thumbnail.height // 2
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(0, 0, 0, 110))
    side = radius * 0.9
    draw.polygon([(cx - side * 0.35, cy - side * 0.5), (cx - side * 0.35, cy + side * 0.5), (cx + side * 0.55, cy)],
                 fill=(255, 255, 255, 235))
    if badge:
        font = ImageFont.load_default(size=13)
        right = draw.textbbox((0, 0), badge, font=font)[2]
        draw.rounded_rectangle((8, thumbnail.height - 30, 24 + right, thumbnail.height - 8), radius=8, fill=(0, 0, 0, 120))
        draw.text((16, thumbnail.height - 27), badge, font=font, fill=(255, 255, 255, 255))
    return thumbnail


def thumbnails_for(image: Image.Image, width: int, badge: str | None) -> list[Image.Image]:
    if image.width >= image.height:
        return [chat_thumbnail(image, width, badge)]
    tall_width = int(width * 0.8)
    return [chat_thumbnail(image, tall_width, badge), chat_thumbnail(center_crop(image, 4 / 5), tall_width, badge)]


def build_sheet(thumbnails: list[Image.Image]) -> Image.Image:
    gap = 20
    row_width = sum(tile.width for tile in thumbnails) + gap * (len(thumbnails) + 1)
    row_height = max(tile.height for tile in thumbnails) + 2 * gap
    sheet = Image.new("RGB", (row_width, row_height * len(BACKGROUNDS)))
    for row, colour in enumerate(BACKGROUNDS.values()):
        sheet.paste(colour, (0, row * row_height, row_width, (row + 1) * row_height))
        left = gap
        for tile in thumbnails:
            sheet.paste(tile, (left, row * row_height + gap))
            left += tile.width + gap
    return sheet


def burn_poster(arguments: argparse.Namespace, ffmpeg: str, ffprobe: str, video: Path) -> Path:
    target = arguments.burn_out or Path("out/final") / f"{video.stem}-poster.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    size = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0:s=x", str(video)], capture_output=True, text=True, check=True).stdout.strip()
    width, height = size.split("x")[:2]
    graph = (f"[1:v]scale={width}:{height}:flags=lanczos:out_color_matrix=bt709:out_range=tv,format=yuv420p[poster];"
             f"[0:v][poster]overlay=0:0:enable='eq(n,0)':format=yuv420,"
             "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv[video]")
    run([ffmpeg, "-v", "error", "-y", "-i", str(video), "-i", str(arguments.burn), "-filter_complex", graph,
         "-map", "[video]", "-map", "0:a?", "-c:v", "libx264", "-preset", "slow", "-crf", str(arguments.crf),
         "-profile:v", "high", "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
         "-color_trc", "bt709", "-color_range", "tv", "-c:a", "copy", "-movflags", "+faststart", str(target)],
        arguments.verbose)
    print(f"wrote {target} (poster on frame 0, video re-encoded at CRF {arguments.crf}, audio copied)")
    return target


def colour_drift(poster: Path, frame: Path) -> float:
    reference = Image.open(poster).convert("RGB")
    actual = Image.open(frame).convert("RGB").resize(reference.size, Image.LANCZOS)
    return sum(ImageStat.Stat(ImageChops.difference(reference, actual)).mean) / 3


def main() -> None:
    arguments = parse_arguments()
    ffmpeg = resolve_binary("ffmpeg", arguments.verbose)
    ffprobe = resolve_binary("ffprobe", arguments.verbose)
    review_dir = arguments.out.parent
    review_dir.mkdir(parents=True, exist_ok=True)
    inputs = list(arguments.inputs) + (render_stills(arguments, review_dir) if arguments.render else [])
    if not inputs:
        sys.exit("give poster images, videos, or --render ids")
    videos = [path for path in inputs if path.suffix.lower() not in IMAGE_SUFFIXES]
    if arguments.burn:
        if len(videos) != 1:
            sys.exit("--burn needs exactly one input video")
        burned = burn_poster(arguments, ffmpeg, ffprobe, videos[0])
        inputs = [burned if path == videos[0] else path for path in inputs]
        videos = [burned]
    badge = arguments.duration or (format_duration(video_duration(ffprobe, videos[0])) if videos else None)
    with tempfile.TemporaryDirectory(prefix="poster-") as folder:
        images = {path: first_frame(ffmpeg, path, Path(folder), arguments.verbose) if path in videos else path for path in inputs}
        if arguments.burn:
            drift = colour_drift(arguments.burn, images[videos[0]])
            verdict = "OK" if drift < 4 else "CHECK: colours shifted (matrix/range mismatch?)"
            print(f"frame 0 vs poster: mean abs difference {drift:.2f} / 255 -> {verdict}")
        thumbnails = [tile for path in inputs for tile in thumbnails_for(Image.open(images[path]), arguments.width, badge)]
    build_sheet(thumbnails).save(arguments.out)
    print(f"wrote {arguments.out} ({len(thumbnails)} thumbnails, light and dark rows{'' if badge else ', no duration badge: pass --duration'})")


if __name__ == "__main__":
    main()
