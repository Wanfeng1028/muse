"""Build the low-poly mesh for the logo reveal.

    uv run --with pillow python3 tools/mesh.py assets/logo.png > assets/mesh.js

FACETS below trace the 16 triangular faces of the Claude Imagine mark in the
512 x 512 logo image. Each face is split along its longest edge until it is
small enough, and every piece takes the average colour of the logo pixels it
covers, so the same geometry works for any colourway of the logo.
For a different mark, replace PTS and FACETS with its own faces.
"""
import json
import random
import sys

from PIL import Image, ImageDraw

PTS = {
    "T": (256, 66), "UR": (413, 164), "LR": (413, 363), "B": (242, 443), "LL": (99, 357), "UL": (99, 164),
    "P1": (192, 232), "P2": (158, 205), "P3": (256, 210), "P4": (320, 164), "P5": (370, 260),
    "P6": (320, 260), "P7": (340, 325), "P8": (280, 297), "P9": (213, 383), "P10": (210, 318), "P11": (148, 282),
}
FACETS = [
    ("UL", "T", "P2"), ("P2", "T", "P1"),
    ("T", "UR", "P4"), ("T", "P4", "P3"), ("P4", "UR", "P3"), ("P3", "UR", "P5"),
    ("UR", "LR", "P5"),
    ("P6", "LR", "P7"), ("P6", "P7", "B"), ("P7", "LR", "B"),
    ("LL", "P8", "P9"), ("P9", "P8", "B"), ("LL", "P9", "B"),
    ("UL", "P11", "LL"), ("UL", "P10", "P11"), ("P11", "P10", "LL"),
]
MAX_AREA = 1500.0

def area(t):
    (ax, ay), (bx, by), (cx, cy) = t
    return abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2

def split(t, rnd):
    if area(t) <= MAX_AREA:
        return [t]
    edges = [(0, 1, 2), (1, 2, 0), (2, 0, 1)]
    i, j, k = max(edges, key=lambda e: (t[e[0]][0] - t[e[1]][0]) ** 2 + (t[e[0]][1] - t[e[1]][1]) ** 2)
    s = rnd.uniform(0.38, 0.62)
    m = (t[i][0] + (t[j][0] - t[i][0]) * s, t[i][1] + (t[j][1] - t[i][1]) * s)
    return split((t[i], m, t[k]), rnd) + split((m, t[j], t[k]), rnd)

def main():
    img = Image.open(sys.argv[1]).convert("RGBA").resize((512, 512), Image.LANCZOS)
    rnd = random.Random(7)
    tris = []
    for f in FACETS:
        for t in split(tuple(PTS[k] for k in f), rnd):
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).polygon([(x, y) for x, y in t], fill=255)
            px = [p for p, m in zip(img.get_flattened_data(), mask.get_flattened_data()) if m > 200 and p[3] > 200]
            if not px:
                px = [img.getpixel((int(sum(x for x, _ in t) / 3), int(sum(y for _, y in t) / 3)))]
            r, g, b = (round(sum(p[c] for p in px) / len(px)) for c in range(3))
            tris.append([round(v, 1) for xy in t for v in xy] + ["#%02x%02x%02x" % (r, g, b)])
    sys.stdout.write("window.MESH = " + json.dumps({"size": 512, "tris": tris}) + ";\n")

main()
