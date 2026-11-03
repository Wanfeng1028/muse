"""Trace the raven artwork into the app icon's master SVG.

Needs numpy, Pillow and vtracer (`pip install vtracer`); see README.md for the exact runs.
usage: python trace.py SOURCE OUT_SVG WORK_PX SPECKLE BLUR
"""

import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import vtracer
from PIL import Image, ImageFilter

INK, PAPER, BLUE = "#101014", "#f2f1ee", "#4e7bfb"


def trace(mask: np.ndarray, speckle: int, d: Path) -> str:
    """One colour layer: vtracer's binary trace of `mask`, as path elements."""
    png, svg = d / "mask.png", d / "mask.svg"
    Image.fromarray(np.where(mask, 0, 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(3)).save(png)
    vtracer.convert_image_to_svg_py(
        str(png), str(svg), colormode="binary", mode="spline", filter_speckle=speckle,
        corner_threshold=60, length_threshold=4.0, splice_threshold=45, path_precision=1,
    )
    found = re.findall(r'<path d="([^"]+)"[^>]*transform="translate\(([-\d.]+),([-\d.]+)\)"', svg.read_text())
    return "".join(f'<path transform="translate({x} {y})" d="{p.strip()}"/>' for p, x, y in found)


def main() -> None:
    src, out, n, speckle, blur = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])
    im = Image.open(src).convert("RGB").resize((n, n), Image.LANCZOS)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    a = np.asarray(im).astype(np.int32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    blue = (b - r > 70) & (b > 150)
    dark = 0.299 * r + 0.587 * g + 0.114 * b < 128

    # Only what lies inside the source's rounded tile (21.5 % corner radius).
    rad = 0.215 * n
    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    inside = (xx - np.clip(xx, rad, n - rad)) ** 2 + (yy - np.clip(yy, rad, n - rad)) ** 2 <= (rad - 2) ** 2

    with tempfile.TemporaryDirectory() as d:
        bird = trace(inside & ~blue, speckle, Path(d))
        ink = trace(inside & ~blue & dark, speckle, Path(d))
    out.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        '<clipPath id="t"><rect width="512" height="512" rx="110"/></clipPath>'
        f'<rect width="512" height="512" rx="110" fill="{BLUE}"/>'
        f'<g clip-path="url(#t)"><g transform="scale({512 / n:g})" fill-rule="evenodd">'
        f'<g fill="{PAPER}">{bird}</g><g fill="{INK}">{ink}</g></g></g></svg>\n',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
