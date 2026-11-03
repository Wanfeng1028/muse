"""Chuan bi anh chup that de dat len video: phong to, bo goc, do bong.

Dung: python prep_shots.py <thu-muc-anh-chup> <thu-muc-cards-dich>
"""
import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

TARGET_W = 1000   # chieu rong tren canvas 1080
MAX_H = 1230      # cao toi da de khong dam vao watermark duoi
RADIUS = 26
SHADOW_PAD = 26


def prep(src, dst):
    im = Image.open(src).convert("RGBA")
    # card qua dai thi thu nho theo chieu cao thay vi tran ra khoi khung
    scale = min(TARGET_W / im.width, MAX_H / im.height)
    im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                   Image.LANCZOS)

    # mask bo goc
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1],
                                           radius=RADIUS, fill=255)
    card = Image.new("RGBA", im.size, (0, 0, 0, 0))
    card.paste(im, (0, 0), mask)

    # do bong
    out = Image.new("RGBA", (im.width + SHADOW_PAD * 2, im.height + SHADOW_PAD * 2),
                    (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [SHADOW_PAD, SHADOW_PAD + 6, SHADOW_PAD + im.width, SHADOW_PAD + im.height + 6],
        radius=RADIUS, fill=(0, 0, 0, 95))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(9)))
    out.alpha_composite(card, (SHADOW_PAD, SHADOW_PAD))

    out.save(dst)
    return out.size


def main():
    src_dir, dst_dir = sys.argv[1], sys.argv[2]
    os.makedirs(dst_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(src_dir, "card*.png")))
    for f in files:
        name = os.path.basename(f)
        size = prep(f, os.path.join(dst_dir, name))
        print(f"{name}: {size[0]}x{size[1]}")


if __name__ == "__main__":
    main()
