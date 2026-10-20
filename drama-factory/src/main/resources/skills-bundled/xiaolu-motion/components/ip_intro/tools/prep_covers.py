"""Cover screenshots / originals -> clean 3:4 cover cards for ip_intro.

  python3 components/ip_intro/tools/prep_covers.py RECIPE.json [--out components/ip_intro/assets/covers]

RECIPE = {"covers": [
  {"key": "token90", "title": "立省90% Token", "src": "/abs/cover.png"},                         # full image (already 3:4)
  {"key": "autoedit", "title": "AI自动剪辑", "src": "/abs/grid.webp", "box": [x0, y0, x1, y1],  # one card of a
   "grid_ui": true},                                                                                  # profile-grid screenshot
  ...
  optional per cover: "inpaint": [[cx, cy, r], ...] discs in source-card pixels, "inpaint_blue": [cx, cy, r]
  (removes a saturated blue/violet badge inside that disc), "blur": [[x0, y0, x1, y1], ...] (strong blur for names)
]}

grid_ui = true (a card cut out of a profile-grid screenshot): the play button (top right) and the
platform watermark (bottom right) are inpainted, the rounded corners are trimmed, then the card is
cut back to exactly 3:4. Output: <key>.jpg (450x600) + covers.json (the manifest ip_intro loads).
Edits are listed per cover in covers.json. Covers stay local (see covers/.gitignore).
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

OUT_W, OUT_H = 450, 600


def to_34(img):
    h, w = img.shape[:2]
    if w * 4 > h * 3:                       # too wide -> trim sides
        nw = int(round(h * 3 / 4))
        x = (w - nw) // 2
        return img[:, x:x + nw]
    nh = int(round(w * 4 / 3))              # too tall -> trim bottom (titles sit at the top)
    return img[:nh]


def process(c):
    src = cv2.imread(c["src"], cv2.IMREAD_COLOR)
    if src is None:
        raise SystemExit(f"cannot read {c['src']}")
    edits = []
    img = src
    if c.get("box"):
        x0, y0, x1, y1 = c["box"]
        img = img[y0:y1, x0:x1].copy()
        edits.append(f"crop {c['box']}")
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    if c.get("grid_ui"):
        cv2.circle(mask, (w - 31, 31), 16, 255, -1)                       # play button
        cv2.rectangle(mask, (w - 50, h - 24), (w - 5, h - 4), 255, -1)     # platform watermark
        edits.append("inpaint play button + watermark")
    for cx, cy, r in c.get("inpaint", []):
        cv2.circle(mask, (int(cx), int(cy)), int(r), 255, -1)
        edits.append(f"inpaint disc {cx},{cy},{r}")
    if c.get("inpaint_blue"):
        cx, cy, r = c["inpaint_blue"]
        disc = np.zeros((h, w), np.uint8)
        cv2.circle(disc, (int(cx), int(cy)), int(r), 255, -1)
        b, g, rr = [img[..., i].astype(int) for i in range(3)]
        blue = ((b - rr > 35) & (b > 120)).astype(np.uint8) * 255
        blue = cv2.bitwise_and(blue, disc)
        cnts, _ = cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            big = max(cnts, key=cv2.contourArea)
            badge = np.zeros_like(blue)
            cv2.drawContours(badge, [cv2.convexHull(big)], -1, 255, -1)  # fills the white glyph inside too
            badge = cv2.dilate(badge, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
            mask = cv2.bitwise_or(mask, badge)
            edits.append(f"inpaint blue badge near {cx},{cy} ({int(cv2.contourArea(big))} px)")
    if mask.any():
        img = cv2.inpaint(img, mask, 7, cv2.INPAINT_TELEA)
    for x0, y0, x1, y1 in c.get("blur", []):
        roi = img[y0:y1, x0:x1]
        k = max(15, (min(roi.shape[:2]) // 3) | 1)
        img[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (k, k), 0)
        edits.append(f"blur {[x0, y0, x1, y1]}")
    if c.get("grid_ui"):
        img = img[7:-7, 7:-7]                                              # rounded corners
        edits.append("trim 7px (rounded corners)")
    img = to_34(img)
    img = cv2.resize(img, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA if img.shape[1] > OUT_W else cv2.INTER_LANCZOS4)
    return img, edits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recipe")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "assets" / "covers"))
    a = ap.parse_args()
    R = json.loads(Path(a.recipe).read_text(encoding="utf-8"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    man = {"version": 1, "note": "local cover cards for ip_intro (not committed)", "covers": []}
    for c in R["covers"]:
        img, edits = process(c)
        fn = f"{c['key']}.jpg"
        cv2.imwrite(str(out / fn), img, [cv2.IMWRITE_JPEG_QUALITY, 93])
        man["covers"].append({"key": c["key"], "file": f"covers/{fn}", "title": c.get("title", ""), "src": c["src"],
                              "grid_ui": bool(c.get("grid_ui")), "edits": edits, "size": [OUT_W, OUT_H]})
        print(c["key"], edits)
    (out / "covers.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out / "covers.json")


if __name__ == "__main__":
    main()
