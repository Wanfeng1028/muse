"""Review helpers for gen_image.py: labelled contact sheets and promoting a picked variant."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from _gen_image_output import archive_existing, existing_outputs

sys.dont_write_bytecode = True

LABEL_HEIGHT = 34
GAP = 8
SHEET_BACKGROUND = (34, 34, 38)
CHECKER = ((205, 205, 205), (235, 235, 235))


def checkerboard(size: int, square: int = 16) -> Image.Image:
    board = Image.new("RGB", (size, size), CHECKER[0])
    draw = ImageDraw.Draw(board)
    for top in range(0, size, square):
        for left in range(0, size, square):
            if (left // square + top // square) % 2:
                draw.rectangle([left, top, left + square - 1, top + square - 1], fill=CHECKER[1])
    return board


def thumbnail(path: Path, cell: int) -> tuple[Image.Image, str]:
    tile = checkerboard(cell)
    if path.suffix.lower() == ".svg":
        ImageDraw.Draw(tile).text((cell // 2 - 30, cell // 2), "SVG (not drawn)", fill=(60, 60, 60))
        return tile, "svg"
    with Image.open(path) as image:
        detail = f"{image.width}x{image.height}{' alpha' if image.mode in ('RGBA', 'LA') else ''}"
        copy = image.convert("RGBA")
    copy.thumbnail((cell, cell), Image.LANCZOS)
    tile.paste(copy, ((cell - copy.width) // 2, (cell - copy.height) // 2), copy)
    return tile, detail


def font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def contact_sheet(paths: list[Path], target: Path, columns: int = 4, cell: int = 320) -> Path:
    images = [path for path in paths if path.is_file()]
    for missing in [path for path in paths if not path.is_file()]:
        print(f"warning: not found, left out of the sheet: {missing}")
    if not images:
        raise SystemExit("error: no images on disk for the contact sheet")
    columns = max(1, min(columns, len(images)))
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGB", (GAP + columns * (cell + GAP), GAP + rows * (cell + LABEL_HEIGHT + GAP)), SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    name_font, detail_font = font(14), font(12)
    for index, path in enumerate(images):
        left = GAP + (index % columns) * (cell + GAP)
        top = GAP + (index // columns) * (cell + LABEL_HEIGHT + GAP)
        tile, detail = thumbnail(path, cell)
        sheet.paste(tile, (left, top))
        draw.text((left + 2, top + cell + 3), path.name[:44], fill=(240, 240, 240), font=name_font)
        draw.text((left + 2, top + cell + 19), detail, fill=(170, 170, 170), font=detail_font)
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)
    print(f"wrote contact sheet {target} ({len(images)} images, {columns}x{rows})")
    return target


def pick(folder: Path, name: str, letter: str) -> int:
    variants = [path for path in existing_outputs(name, folder) if path.stem != name]
    chosen = [path for path in variants if path.stem == f"{name}.{letter}"]
    if not chosen:
        found = ", ".join(path.name for path in variants) or "none"
        print(f"error: no variant {name}.{letter}.* in {folder} (found: {found})", file=sys.stderr)
        return 1
    source = chosen[0]
    target = folder / f"{name}{source.suffix}"
    archive_existing(target)
    source.rename(target)
    sidecar = source.with_name(source.name + ".json")
    if sidecar.exists():
        sidecar.rename(target.with_name(target.name + ".json"))
    print(f"picked {source.name} -> {target}")
    for other in variants:
        if other != source:
            archive_existing(other)
    return 0
