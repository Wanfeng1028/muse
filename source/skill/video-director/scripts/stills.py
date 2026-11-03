#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.1"]
# ///
"""Render chosen seconds of a Remotion composition in one batched call and tile them into a labelled contact sheet.

Inputs: composition id, output PNG, times in seconds. Run from the Remotion project root.
Output: the sheet PNG (default under out/review/), one tile per time, labelled with seconds and frame.
Example: stills.py Wide out/review/hook.png 0 0.5 1 2.5 4 --fps 30 --props '{"voice":"sofia"}'
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LABEL_HEIGHT_RATIO = 0.07
GAP = 6


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("composition", help="Remotion composition id")
    parser.add_argument("output", type=Path, help="sheet PNG to write, e.g. out/review/sheet.png")
    parser.add_argument("times", nargs="+", type=float, help="times in seconds")
    parser.add_argument("--fps", type=float, default=30, help="composition fps (default 30)")
    parser.add_argument("--scale", type=float, default=0.5, help="render scale (default 0.5)")
    parser.add_argument("--props", help="input props JSON passed to Remotion")
    parser.add_argument("--entry", help="entry point (default: the project's Remotion config)")
    parser.add_argument("--columns", type=int, help="columns (default: 3 landscape, 4 square, 5 portrait)")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def frames_for(times: list[float], fps: float) -> list[int]:
    return sorted({max(0, round(time * fps)) for time in times})


def remotion_base(arguments: argparse.Namespace, command: str) -> list[str]:
    base = ["npx", "remotion", command]
    if arguments.entry:
        base.append(arguments.entry)
    return base


def remotion_flags(arguments: argparse.Namespace) -> list[str]:
    flags = [f"--scale={arguments.scale}", "--image-format=png", "--log=error"]
    if arguments.props:
        flags.append(f"--props={arguments.props}")
    return flags


def run(command: list[str], verbose: bool) -> subprocess.CompletedProcess[str]:
    if verbose:
        print("$", " ".join(command), file=sys.stderr)
    return subprocess.run(command, capture_output=True, text=True)


def render_batched(arguments: argparse.Namespace, frames: list[int], folder: Path) -> dict[int, Path] | None:
    selection = ",".join(str(frame) for frame in frames) if len(frames) > 1 else f"{frames[0]}-{frames[0]}"
    command = remotion_base(arguments, "render") + [
        arguments.composition, str(folder), "--sequence", f"--frames={selection}", *remotion_flags(arguments),
    ]
    result = run(command, arguments.verbose)
    if result.returncode != 0 and "--frames" not in result.stderr:
        sys.exit(f"remotion render failed:\n{result.stderr[-2000:]}")
    if result.returncode != 0:
        return None
    rendered: dict[int, Path] = {}
    for path in folder.glob("*.png"):
        match = re.search(r"(\d+)\.png$", path.name)
        if match:
            rendered[int(match.group(1))] = path
    return rendered if all(frame in rendered for frame in frames) else None


def render_one_by_one(arguments: argparse.Namespace, frames: list[int], folder: Path) -> dict[int, Path]:
    print("this Remotion version rejects a frame list; falling back to one still per frame (slower, re-bundles each time)", file=sys.stderr)
    rendered: dict[int, Path] = {}
    for frame in frames:
        target = folder / f"still-{frame:06d}.png"
        command = remotion_base(arguments, "still") + [
            arguments.composition, str(target), f"--frame={frame}", *remotion_flags(arguments),
        ]
        result = run(command, arguments.verbose)
        if result.returncode != 0:
            sys.exit(f"remotion still failed at frame {frame}:\n{result.stderr[-2000:]}")
        rendered[frame] = target
    return rendered


def auto_columns(width: int, height: int, count: int) -> int:
    aspect = width / height
    columns = 3 if aspect >= 1.2 else 4 if aspect > 0.85 else 5
    return max(1, min(columns, count))


def label_tile(image: Image.Image, text: str) -> Image.Image:
    tile = image.convert("RGB")
    draw = ImageDraw.Draw(tile, "RGBA")
    size = max(12, int(min(tile.size) * LABEL_HEIGHT_RATIO))
    font = ImageFont.load_default(size=size)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    padding = size // 3
    draw.rectangle((0, 0, right - left + 2 * padding, bottom - top + 2 * padding), fill=(0, 0, 0, 170))
    draw.text((padding - left, padding - top), text, font=font, fill=(255, 255, 255, 255))
    return tile


def build_sheet(tiles: list[Image.Image], columns: int) -> Image.Image:
    width, height = tiles[0].size
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * width + (columns + 1) * GAP, rows * height + (rows + 1) * GAP), (255, 255, 255))
    for index, tile in enumerate(tiles):
        column, row = index % columns, index // columns
        sheet.paste(tile, (GAP + column * (width + GAP), GAP + row * (height + GAP)))
    return sheet


def main() -> None:
    arguments = parse_arguments()
    frames = frames_for(arguments.times, arguments.fps)
    with tempfile.TemporaryDirectory(prefix="stills-") as folder_name:
        folder = Path(folder_name) / "frames"
        rendered = render_batched(arguments, frames, folder)
        if rendered is None:
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True, exist_ok=True)
            rendered = render_one_by_one(arguments, frames, folder)
        tiles = [label_tile(Image.open(rendered[frame]), f"{frame / arguments.fps:.2f}s  f{frame}") for frame in frames]
    columns = arguments.columns or auto_columns(*tiles[0].size, len(tiles))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    build_sheet(tiles, columns).save(arguments.output)
    print(f"{arguments.output} ({len(tiles)} stills, {columns} columns, frames {','.join(map(str, frames))})")


if __name__ == "__main__":
    main()
