#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["rembg[cpu]>=2.0.60", "pillow>=10.1", "numpy>=1.26"]
# ///
"""Cut subjects out of a plain backdrop with BiRefNet (MIT licence) for compositing in Remotion, apps or pages.

Per image: rembg `birefnet-general` matte (skipped when the file already has real alpha), alpha remap
(a - floor) / span to kill faint fringes, optional erode/feather, edge colour decontamination against the backdrop
colour (removes the white halo: C = (C_obs - (1 - a) * B) / a), trim to the alpha box plus a margin, and a review copy
over saturated violet. Halos and holes are invisible on white and obvious on colour: always look at the check/ copies.

Warnings it prints:
  - subject shares the backdrop colour (white shirt, white sneakers, white mug on white): regenerate on mid-grey #808080
    or chroma green #00B140 (gen_image.py "background": "grey" | "green") and run again; the matte will keep it.
  - enclosed transparent holes inside the subject: fine for gaps between arms, a defect inside garments or eyes.
Only BiRefNet (MIT) by default. Do not switch to BRIA RMBG-2.0 (CC BY-NC) without a commercial licence.
The first run downloads the model (about 1 GB) into the rembg cache (~/.rembg/models, older rembg: ~/.u2net).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

EXAMPLE = "example: cutout.py public/img/hero.png public/img/cast.png --erode 1 --json"
VIOLET = "#8342C9"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BiRefNet background removal: trimmed RGBA cutouts, halo decontamination and review composites.",
        epilog=__doc__.split("\n\n", 1)[1] + f"\noutputs: <out-dir>/<name>.png (RGBA, trimmed), <check-dir>/<name>.png (RGB review)\n{EXAMPLE}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("images", nargs="+", type=Path, help="input images (png/jpg/webp) on a plain backdrop, or with native alpha")
    parser.add_argument("--out-dir", type=Path, help="cutout folder (default: <image dir>/cut)")
    parser.add_argument("--check-dir", type=Path, help="review folder (default: <image dir>/check)")
    parser.add_argument("--check-color", default=VIOLET, help=f"saturated review backdrop, hex (default {VIOLET} violet)")
    parser.add_argument("--backdrop", default="auto", help="backdrop colour for decontamination: auto (image border median) or #RRGGBB")
    parser.add_argument("--no-decontaminate", action="store_true", help="skip edge colour decontamination")
    parser.add_argument("--erode", type=int, default=0, help="shrink alpha by this many px before feathering (default 0; 1 kills most halos)")
    parser.add_argument("--feather", type=float, default=0.0, help="Gaussian alpha feather in px after erode (default 0; 0.5-1 softens)")
    parser.add_argument("--margin", type=int, default=12, help="px kept around the alpha bbox (default 12)")
    parser.add_argument("--alpha-floor", type=float, default=0.08, help="alpha below this becomes 0 (default 0.08)")
    parser.add_argument("--alpha-span", type=float, default=0.84, help="alpha remap span: (a-floor)/span (default 0.84)")
    parser.add_argument("--force-matte", action="store_true", help="matte even when the input already has real alpha")
    parser.add_argument("--model", default="birefnet-general", help="rembg session name (default birefnet-general, MIT)")
    parser.add_argument("--json", action="store_true", help="also write <out-dir>/cutout-report.json")
    return parser.parse_args()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    digits = value.lstrip("#")
    if len(digits) != 6:
        raise ValueError(f"colour must be #RRGGBB, got {value}")
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def border_color(rgb: np.ndarray) -> np.ndarray:
    frame = np.concatenate([rgb[:2].reshape(-1, 3), rgb[-2:].reshape(-1, 3), rgb[:, :2].reshape(-1, 3), rgb[:, -2:].reshape(-1, 3)])
    return np.median(frame, axis=0)


def has_real_alpha(image: Image.Image) -> bool:
    if image.mode not in ("RGBA", "LA", "PA") and "transparency" not in image.info:
        return False
    return float((np.asarray(image.convert("RGBA").getchannel("A")) == 0).mean()) > 0.01


def matte(source: Image.Image, session_factory: "SessionFactory", force: bool) -> tuple[np.ndarray, np.ndarray, str]:
    if has_real_alpha(source) and not force:
        rgba = np.asarray(source.convert("RGBA")).astype(np.float32)
        return rgba[..., :3], rgba[..., 3] / 255.0, "native alpha (no matte)"
    from rembg import remove
    rgb_image = source.convert("RGB")
    alpha = np.asarray(remove(rgb_image, session=session_factory.get(), only_mask=True).convert("L")).astype(np.float32) / 255.0
    return np.asarray(rgb_image).astype(np.float32), alpha, "BiRefNet matte"


def refine_alpha(raw: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    alpha = np.clip((raw - args.alpha_floor) / args.alpha_span, 0, 1)
    image = Image.fromarray((alpha * 255).round().astype(np.uint8), "L")
    for _ in range(max(0, args.erode)):
        image = image.filter(ImageFilter.MinFilter(3))
    if args.feather > 0:
        image = image.filter(ImageFilter.GaussianBlur(args.feather))
    return np.asarray(image).astype(np.float32) / 255.0


def decontaminate(rgb: np.ndarray, raw_alpha: np.ndarray, backdrop: np.ndarray) -> tuple[np.ndarray, int]:
    edge = (raw_alpha > 0.1) & (raw_alpha < 0.98)
    coverage = np.clip(raw_alpha, 0.1, 1.0)[..., None]
    cleaned = np.clip((rgb - (1 - coverage) * backdrop) / coverage, 0, 255)
    result = rgb.copy()
    result[edge] = cleaned[edge]
    return result, int(edge.sum())


def backdrop_share(rgb: np.ndarray, alpha: np.ndarray, backdrop: np.ndarray) -> float:
    solid = alpha > 0.9
    if not solid.any():
        return 0.0
    distance = np.abs(rgb[solid] - backdrop).max(axis=1)
    return float((distance < 24).mean())


def enclosed_holes(alpha: np.ndarray) -> int:
    transparent = np.where(alpha <= 0.03, 255, 0).astype(np.uint8)
    padded = Image.fromarray(np.pad(transparent, 1, constant_values=255), "L").copy()
    ImageDraw.floodfill(padded, (0, 0), 128)
    return int((np.asarray(padded)[1:-1, 1:-1] == 255).sum())


def trim(image: Image.Image, margin: int) -> Image.Image:
    box = image.getchannel("A").point(lambda value: 255 if value > 8 else 0).getbbox()
    if not box:
        return image
    left, top, right, bottom = box
    return image.crop((max(0, left - margin), max(0, top - margin), min(image.width, right + margin), min(image.height, bottom + margin)))


def review_composite(cut: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    backdrop = Image.new("RGBA", cut.size, (*color, 255))
    backdrop.alpha_composite(cut)
    return backdrop.convert("RGB")


class SessionFactory:
    def __init__(self, model: str) -> None:
        self.model = model
        self.session: object | None = None

    def get(self) -> object:
        if self.session is None:
            from rembg import new_session
            self.session = new_session(self.model)
        return self.session


def warnings_for(share: float, holes: int, subject_pixels: int, backdrop: np.ndarray) -> list[str]:
    messages = []
    if share > 0.02:
        hex_value = "#{:02X}{:02X}{:02X}".format(*backdrop.round().astype(int))
        messages.append(f"{share:.0%} of the subject matches the backdrop {hex_value}: risk of holes. If the check copy shows "
                        "gaps, regenerate on mid-grey #808080 or chroma green #00B140 (gen_image.py background grey/green)")
    if subject_pixels and holes / subject_pixels > 0.005:
        messages.append(f"{holes} px of enclosed transparent holes ({holes / subject_pixels:.1%} of the subject): "
                        "fine between arms or legs, a defect inside garments, faces or eyes")
    return messages


def process(path: Path, sessions: SessionFactory, args: argparse.Namespace, check_color: tuple[int, int, int]) -> dict:
    out_dir = args.out_dir or path.parent / "cut"
    check_dir = args.check_dir or path.parent / "check"
    out_dir.mkdir(parents=True, exist_ok=True)
    check_dir.mkdir(parents=True, exist_ok=True)
    source = Image.open(path)
    rgb, raw_alpha, method = matte(source, sessions, args.force_matte)
    backdrop = border_color(rgb) if args.backdrop == "auto" else np.array(hex_to_rgb(args.backdrop), dtype=np.float32)
    alpha = refine_alpha(raw_alpha, args)
    edge_pixels = 0
    if not args.no_decontaminate and method != "native alpha (no matte)":
        rgb, edge_pixels = decontaminate(rgb, raw_alpha, backdrop)
    rgba = np.dstack([rgb, alpha * 255]).round().astype(np.uint8)
    cut = trim(Image.fromarray(rgba, "RGBA"), args.margin)
    cut_path, check_path = out_dir / f"{path.stem}.png", check_dir / f"{path.stem}.png"
    cut.save(cut_path)
    review_composite(cut, check_color).save(check_path)
    subject_pixels = int((alpha > 0.5).sum())
    holes = enclosed_holes(alpha)
    share = backdrop_share(np.asarray(source.convert("RGB")).astype(np.float32), raw_alpha, backdrop) if method != "native alpha (no matte)" else 0.0
    warnings = warnings_for(share, holes, subject_pixels, backdrop)
    coverage = float((np.asarray(cut.getchannel("A")) > 8).mean())
    print(f"{path.name}: {method}, {source.width}x{source.height} -> {cut.width}x{cut.height}, opaque {coverage:.0%}, "
          f"decontaminated {edge_pixels} edge px")
    for message in warnings:
        print(f"  warning: {message}")
    print(f"  wrote {cut_path}\n  wrote {check_path}")
    return {"input": str(path), "cutout": str(cut_path), "check": str(check_path), "method": method,
            "size": [cut.width, cut.height], "opaque_share": round(coverage, 4), "decontaminated_edge_pixels": edge_pixels,
            "backdrop": [round(float(value), 1) for value in backdrop], "backdrop_colour_share_in_subject": round(share, 4),
            "enclosed_hole_pixels": holes, "warnings": warnings}


def main() -> int:
    args = parse_args()
    try:
        check_color = hex_to_rgb(args.check_color)
        if args.backdrop != "auto":
            hex_to_rgb(args.backdrop)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    missing = [str(path) for path in args.images if not path.is_file()]
    if missing:
        print(f"error: not found: {', '.join(missing)}", file=sys.stderr)
        return 1
    sessions = SessionFactory(args.model)
    reports = [process(path, sessions, args, check_color) for path in args.images]
    if args.json:
        report_path = (args.out_dir or args.images[0].parent / "cut") / "cutout-report.json"
        report_path.write_text(json.dumps(reports, indent=2))
        print(f"wrote {report_path}")
    flagged = sum(1 for report in reports if report["warnings"])
    print(f"{len(reports)} cut, {flagged} with warnings (look at the check/ copies before using them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
