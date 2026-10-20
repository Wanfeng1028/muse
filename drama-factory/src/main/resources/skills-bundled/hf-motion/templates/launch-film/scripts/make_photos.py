"""Draw the launch-film placeholder photos (original, deterministic, PIL+numpy).

Nine abstract 1440x1440 scenes painted only in the three default palette
colours and blends of them (a photo is user content, so its blends are exempt
from the three-colour rule). They stand in for the user's photos; ask for
real ones and pass photos=a.jpg|b.jpg|... instead.

    python3 scripts/make_photos.py --out assets/photos            # shipped set
    python3 scripts/make_photos.py --out /tmp/alt --variant 1     # a different 9
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

N = 1440
PAPER, CHAR, RED = np.array([242, 238, 230.0]), np.array([30, 30, 30.0]), np.array([229, 50, 45.0])


def mix(a, b, k):
    return tuple(int(round(v)) for v in a * (1 - k) + b * k)


def scene(i, rng):
    im = Image.new("RGB", (N, N))
    d = ImageDraw.Draw(im)
    # vertical sky/ground gradient between two palette blends
    top, bot = mix(PAPER, RED, rng.uniform(0.05, 0.3)), mix(PAPER, CHAR, rng.uniform(0.1, 0.4))
    for y in range(N):
        d.line([(0, y), (N, y)], fill=mix(np.array(top), np.array(bot), y / N))
    kind = i % 9
    if kind == 0:  # sun over layered hills
        d.ellipse([820, 300, 1160, 640], fill=mix(RED, PAPER, 0.15))
        for k, h in enumerate([900, 1020, 1150]):
            pts = [(x, h + 90 * np.sin(x / (260 + 80 * k) + k)) for x in range(0, N + 40, 40)]
            d.polygon(pts + [(N, N), (0, N)], fill=mix(CHAR, PAPER, 0.55 - 0.2 * k))
    elif kind == 1:  # towers with lit windows
        for k in range(6):
            x0 = 80 + k * 220 + int(rng.integers(-30, 30)); h = int(rng.integers(500, 1100))
            d.rectangle([x0, N - h, x0 + 180, N], fill=mix(CHAR, PAPER, 0.1 * (k % 3)))
            for wy in range(N - h + 40, N - 40, 70):
                for wx in range(x0 + 25, x0 + 160, 50):
                    if rng.random() < 0.55:
                        d.rectangle([wx, wy, wx + 26, wy + 36], fill=mix(PAPER, RED, rng.uniform(0, 0.4)))
    elif kind == 2:  # sea and horizon
        d.rectangle([0, 760, N, N], fill=mix(CHAR, RED, 0.12))
        for y in range(790, N, 34):
            d.line([(0, y), (N, y + 10)], fill=mix(PAPER, CHAR, 0.45 + 0.4 * (y - 760) / 680), width=5)
        d.ellipse([560, 560, 880, 880], fill=mix(RED, PAPER, 0.3))
        d.rectangle([0, 720, N, 760], fill=mix(PAPER, RED, 0.2))
    elif kind == 3:  # still life
        d.rectangle([0, 960, N, N], fill=mix(CHAR, PAPER, 0.25))
        d.ellipse([420, 420, 760, 1000], fill=mix(CHAR, PAPER, 0.05))
        d.rectangle([530, 300, 650, 520], fill=mix(CHAR, PAPER, 0.05))
        for cx in (860, 1010, 940):
            d.ellipse([cx - 90, 820 - (cx == 940) * 120, cx + 90, 1000 - (cx == 940) * 120], fill=mix(RED, CHAR, rng.uniform(0, 0.3)))
    elif kind == 4:  # concentric arcs
        for k in range(12, 0, -1):
            r = k * 110
            d.ellipse([N / 2 - r, N - r, N / 2 + r, N + r], fill=mix(PAPER, RED if k % 2 else CHAR, 0.12 + 0.05 * k))
    elif kind == 5:  # mountain with snow cap
        d.polygon([(100, 1200), (720, 360), (1340, 1200)], fill=mix(CHAR, PAPER, 0.2))
        d.polygon([(600, 520), (720, 360), (840, 520), (760, 490), (700, 540)], fill=mix(PAPER, CHAR, 0.03))
        d.rectangle([0, 1180, N, N], fill=mix(CHAR, RED, 0.25))
    elif kind == 6:  # plant leaves
        for k in range(14):
            a = rng.uniform(-1.2, 1.2); L = rng.uniform(300, 560)
            x1, y1 = 720 + L * np.sin(a), 1300 - L * np.cos(a)
            d.line([(720, 1300), (x1, y1)], fill=mix(CHAR, PAPER, 0.2), width=10)
            d.ellipse([x1 - 70, y1 - 120, x1 + 70, y1 + 120], fill=mix(CHAR, RED, rng.uniform(0.05, 0.3)))
        d.rectangle([560, 1250, 880, N], fill=mix(RED, CHAR, 0.2))
    elif kind == 7:  # stairs in raking light
        for k in range(10):
            d.rectangle([k * 144, 1440 - (k + 1) * 120, N, 1440 - k * 120], fill=mix(PAPER, CHAR, 0.15 + 0.06 * k))
            d.rectangle([k * 144, 1440 - (k + 1) * 120, N, 1440 - (k + 1) * 120 + 16], fill=mix(PAPER, RED, 0.25))
    else:  # window light on a wall
        for k in range(3):
            x0 = 260 + k * 330
            d.polygon([(x0, 200), (x0 + 240, 200), (x0 + 520, 1300), (x0 + 280, 1300)], fill=mix(PAPER, RED, 0.18))
        d.rectangle([0, 1250, N, N], fill=mix(CHAR, PAPER, 0.35))
    im = im.filter(ImageFilter.GaussianBlur(2.2))
    grain = rng.normal(0, 2.5, (N, N, 1))  # film grain so it reads as a photo
    arr = np.clip(np.asarray(im, dtype=np.float64) + grain, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="assets/photos")
    ap.add_argument("--variant", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for i in range(9):
        rng = np.random.default_rng(719 + 100 * a.variant + i)
        scene(i + 4 * a.variant, rng).save(os.path.join(a.out, f"photo-{a.variant}{i + 1}.jpg"), quality=84, optimize=True)
    print("wrote 9 photos to", a.out)


if __name__ == "__main__":
    main()
