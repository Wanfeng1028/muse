"""Pixel QA for any finished video (no bbox data needed), used as a gate.

  python3 -m qa.pixel_qa VIDEO --start 0 --end 25 --step 0.5 --profile xhs_3x4 \
         [--srt captions.srt] --out-dir DIR

Per sampled frame, Apple Vision (qa/vision_probe.swift, on-device) finds faces (+ lips),
text lines (zh-Hans/en) and rectangles (cards); frame pixels come from ffmpeg.
Rules (every hit is a gate failure; nothing is a mere warning):
  face_cover     text over a face box, or a card edge cutting through a face
  mouth_cover    any text / card edge in the mouth zone (lower third of the face box)
  caption_band   non-caption text, a card, or a face (PiP) inside the caption band (74–86 % H)
  top_persistent the same text stays in the top band for >= 80 % of samples and >= 10 s
  empty_card     a card (>= 2.5 % of the frame, no face) whose body is mostly blank
  overlap        text over text, text straddling a card edge, cards partially overlapping
Captions are recognised by matching OCR lines against the SRT text (timing ignored), so a
caption in the band is fine and a caption elsewhere is reported (caption_misplaced, gate).
Writes DIR/pixel_qa_report.json and DIR/pixel_qa_*.png (annotated problem frames).
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from render.common import save_json, video_info
from timeline.anchors import norm
from .vision import analyze
from .zones import area, contains, inter, mouth_zone, profile, rnd

RULES = ["face_cover", "mouth_cover", "caption_band", "caption_misplaced", "top_persistent", "empty_card", "overlap"]


def read_srt(path):
    txt = Path(path).read_text(encoding="utf-8", errors="ignore")
    lines = []
    for block in re.split(r"\n\s*\n", txt):
        ls = [l.strip() for l in block.strip().splitlines()]
        ls = [l for l in ls if l and not l.isdigit() and "-->" not in l]
        if ls:
            lines.append(norm("".join(ls)))
    return [l for l in lines if l]


def is_caption(text, caps):
    """an OCR line is a caption when it reproduces (most of) one SRT line; short card labels that
    merely occur inside a caption ("信息卡" in "字幕、信息卡") do not count"""
    n = norm(text)
    if len(n) < 3 or not caps:
        return False
    for c in caps:
        if difflib.SequenceMatcher(a=n, b=c, autojunk=False).ratio() >= 0.8:
            return True
        if (n in c and len(n) >= 0.8 * len(c)) or (c in n and len(c) >= 0.8 * len(n)):
            return True
    return False


def decode_frames(video, frames, W, H):
    sel = "+".join(f"eq(n\\,{n})" for n in frames)
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"select='{sel}'", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True)
    arr = np.frombuffer(r.stdout, np.uint8)
    k = arr.size // (W * H * 3)
    return {n: arr[i * W * H * 3:(i + 1) * W * H * 3].reshape(H, W, 3) for i, n in enumerate(frames[:k])}


def emptiness(img, b, thr=28, grid=8):
    """fraction of the card body (inset 6 %) that is blank: 8x8 cells with (dilated) ink < 1 %"""
    H, W = img.shape[:2]
    x0, y0 = int(max(0, b["x"] + b["w"] * 0.06)), int(max(0, b["y"] + b["h"] * 0.06))
    x1, y1 = int(min(W, b["x"] + b["w"] * 0.94)), int(min(H, b["y"] + b["h"] * 0.94))
    if x1 - x0 < 16 or y1 - y0 < 16:
        return 0.0, 1.0
    roi = img[y0:y1, x0:x1].astype(np.int16)
    med = np.median(roi.reshape(-1, 3), axis=0)
    ink = (np.abs(roi - med).max(2) > thr).astype(np.uint8)
    ink = cv2.dilate(ink, np.ones((9, 9), np.uint8))
    hh, ww = ink.shape
    cells = [ink[int(r * hh / grid):int((r + 1) * hh / grid), int(c * ww / grid):int((c + 1) * ww / grid)].mean() for r in range(grid) for c in range(grid)]
    return float(np.mean([c < 0.01 for c in cells])), float(ink.mean())


def edge_contrast(img, b, side, lo, hi):
    """mean |inside - outside| (max over RGB) across one card edge, over [lo, hi] along the edge.
    Real overlay edges are consistent steps; a Vision rectangle guessed inside a photo is not."""
    H, W = img.shape[:2]
    lo, hi = int(max(0, lo)), int(min(H if side in ("l", "r") else W, hi))
    if hi - lo < 4:
        return 0.0
    if side in ("l", "r"):
        x = int(round(b["x"] if side == "l" else b["x"] + b["w"]))
        if x < 5 or x > W - 5:
            return 0.0
        a, c = img[lo:hi, x - 5:x - 1].astype(np.int16).mean(1), img[lo:hi, x + 1:x + 5].astype(np.int16).mean(1)
    else:
        y = int(round(b["y"] if side == "t" else b["y"] + b["h"]))
        if y < 5 or y > H - 5:
            return 0.0
        a, c = img[y - 5:y - 1, lo:hi].astype(np.int16).mean(0), img[y + 1:y + 5, lo:hi].astype(np.int16).mean(0)
    return float(np.median(np.abs(a - c).max(1)))


def crossing_edges(card, box):
    """card edges that pass through the interior of box -> [(side, lo, hi)]"""
    out = []
    x0, x1, y0, y1 = box["x"], box["x"] + box["w"], box["y"], box["y"] + box["h"]
    for side, x in (("l", card["x"]), ("r", card["x"] + card["w"])):
        if x0 + 2 < x < x1 - 2 and card["y"] < y1 and card["y"] + card["h"] > y0:
            out.append((side, max(y0, card["y"]), min(y1, card["y"] + card["h"])))
    for side, y in (("t", card["y"]), ("b", card["y"] + card["h"])):
        if y0 + 2 < y < y1 - 2 and card["x"] < x1 and card["x"] + card["w"] > x0:
            out.append((side, max(x0, card["x"]), min(x1, card["x"] + card["w"])))
    return out


def real_crossing(img, card, box, thr=18):
    return [e for e in crossing_edges(card, box) if edge_contrast(img, card, *e) >= thr]


def frame_elements(f, W, H, caps):
    faces = [{"box": x["box"], "mouth": x.get("mouth")} for x in f.get("faces", []) if x.get("conf", 1) >= 0.5 and x["box"]["w"] >= 40]
    texts = []
    for x in f.get("texts", []):
        if x["conf"] < 0.3 or not x["text"].strip():
            continue
        b = x["box"]
        cap_geo = b["h"] >= 0.03 * H and abs(b["x"] + b["w"] / 2 - W / 2) <= 0.15 * W   # caption-sized, centred line
        texts.append({"box": b, "text": x["text"], "caption": cap_geo and is_caption(x["text"], caps)})
    cards = []
    for x in f.get("rects", []):
        b = x["box"]
        a = area(b) / (W * H)
        if x["conf"] < 0.8 or a < 0.015 or a > 0.9:
            continue
        cards.append({"box": b})
    # rects found inside the picture of a person (the smallest card holding a face) are image content, not layout
    holders = []
    for fc in faces:
        cs = [c for c in cards if contains(c["box"], fc["box"], 6)]
        if cs:
            holders.append(min(cs, key=lambda c: area(c["box"])))
    cards = [c for c in cards if not any(h is not c and contains(h["box"], c["box"], 16) for h in holders)]
    return faces, texts, cards


def check_frame(n, t, img, faces, texts, cards, Z, empty_thr):
    v = []
    W, H = Z["W"], Z["H"]
    band = Z["caption_band"]
    add = lambda rule, what, box, extra=None: v.append({"rule": rule, "n": n, "t": round(t, 3), "what": what, "box": rnd(box), **(extra or {})})
    for fc in faces:
        fb, mz = fc["box"], mouth_zone(fc["box"])
        for tx in texts:
            ia = inter(tx["box"], fb)
            if ia > 0.02 * area(fb) or ia > 0.15 * area(tx["box"]):
                add("face_cover", f"text '{tx['text']}' over face", tx["box"], {"face": rnd(fb)})
            if inter(tx["box"], mz) > 0.01 * area(mz):
                add("mouth_cover", f"text '{tx['text']}' in mouth zone", tx["box"], {"mouth_zone": rnd(mz)})
        for cd in cards:
            ia = inter(cd["box"], fb)
            if ia > 0.05 * area(fb) and not contains(cd["box"], fb, 6) and real_crossing(img, cd["box"], fb):
                add("face_cover", "card edge cuts through a face", cd["box"], {"face": rnd(fb), "overlap_px": round(ia)})
                if real_crossing(img, cd["box"], mz):
                    add("mouth_cover", "card edge in mouth zone", cd["box"], {"mouth_zone": rnd(mz)})
        if inter(fb, band) > 0.2 * fb["h"] * fb["w"]:
            add("caption_band", "face / person picture inside caption band", fb)
    for tx in texts:
        inb = inter(tx["box"], band) / max(1.0, area(tx["box"]))
        if not tx["caption"] and inb >= 0.3:
            add("caption_band", f"non-caption text '{tx['text']}' in caption band", tx["box"])
        if tx["caption"] and inb < 0.5:
            add("caption_misplaced", f"caption '{tx['text']}' outside the caption band", tx["box"])
    for cd in cards:
        b = cd["box"]
        yi = max(0.0, min(b["y"] + b["h"], band["y"] + band["h"]) - max(b["y"], band["y"]))
        if yi >= 0.2 * band["h"] and inter(b, band) >= 0.05 * area(b):
            add("caption_band", "card inside caption band", b)
        if area(b) >= 0.025 * W * H and not any(inter(b, fc["box"]) > 0 for fc in faces):
            ef, ink = emptiness(img, b)
            if ef >= empty_thr:
                add("empty_card", f"card body {ef:.0%} blank", b, {"blank_frac": round(ef, 3), "ink": round(ink, 4)})
    # overlaps
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            ia = inter(a["box"], b["box"])
            if ia > 0.2 * min(area(a["box"]), area(b["box"])):
                add("overlap", f"text '{a['text']}' overlaps text '{b['text']}'", a["box"], {"other": rnd(b["box"])})
    for tx in texts:
        for cd in cards:
            fr = inter(tx["box"], cd["box"]) / max(1.0, area(tx["box"]))
            if 0.15 < fr < 0.85 and real_crossing(img, cd["box"], tx["box"]):
                add("overlap", f"text '{tx['text']}' straddles a card edge ({fr:.0%} inside)", tx["box"], {"card": rnd(cd["box"])})
    for i, a in enumerate(cards):
        for b in cards[i + 1:]:
            ia = inter(a["box"], b["box"])
            if ia > 0.02 * min(area(a["box"]), area(b["box"])) and not contains(a["box"], b["box"], 6) and not contains(b["box"], a["box"], 6):
                add("overlap", "cards partially overlap", a["box"], {"other": rnd(b["box"]), "overlap_px": round(ia)})
    return v


def persistent_top(samples, Z, times):
    P = Z["persistent_top"]
    seen = {}
    for (n, t), texts in samples:
        for tx in texts:
            b = tx["box"]
            if b["y"] + b["h"] / 2 > Z["top_band"]["h"]:
                continue
            k = norm(tx["text"])
            if len(k) < 2:
                continue
            s = seen.setdefault(k, {"text": tx["text"], "frames": [], "box": b})
            s["frames"].append((n, t))
    out = []
    span_all = max(times) - min(times) if times else 0
    for k, s in seen.items():
        ratio = len({n for n, _ in s["frames"]}) / max(1, len(times))
        ts = [t for _, t in s["frames"]]
        span = max(ts) - min(ts)
        if ratio >= P["min_ratio"] and span >= min(P["min_span_s"], 0.8 * span_all):
            out.append({"rule": "top_persistent", "n": s["frames"][0][0], "t": round(min(ts), 3), "what": f"top text '{s['text']}' on screen in {ratio:.0%} of samples ({min(ts):.1f}–{max(ts):.1f}s)",
                        "box": rnd(s["box"]), "ratio": round(ratio, 3), "span_s": round(span, 2)})
    return out


def _font(sz):
    for f in ["/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/SFNSMono.ttf"]:
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def annotate(img, Z, faces, texts, cards, viol, title):
    im = Image.fromarray(img).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    bd = Z["caption_band"]
    d.rectangle([bd["x"], bd["y"], bd["x"] + bd["w"], bd["y"] + bd["h"]], fill=(255, 210, 0, 60), outline=(255, 190, 0, 255), width=3)
    d.line([0, Z["top_band"]["h"], Z["W"], Z["top_band"]["h"]], fill=(255, 190, 0, 200), width=2)
    for fc in faces:
        b, m = fc["box"], mouth_zone(fc["box"])
        d.rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], outline=(40, 140, 255, 255), width=4)
        d.rectangle([m["x"], m["y"], m["x"] + m["w"], m["y"] + m["h"]], fill=(255, 0, 200, 50), outline=(255, 0, 200, 255), width=2)
    for c in cards:
        b = c["box"]
        d.rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], outline=(0, 200, 90, 200), width=2)
    for tx in texts:
        b = tx["box"]
        d.rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], outline=(0, 170, 170, 220) if tx["caption"] else (0, 200, 90, 220), width=2)
    for x in viol:
        b = x["box"]
        d.rectangle([b["x"] - 3, b["y"] - 3, b["x"] + b["w"] + 3, b["y"] + b["h"] + 3], outline=(255, 40, 40, 255), width=6)
    im = Image.alpha_composite(im, ov).convert("RGB")
    bar = Image.new("RGB", (im.width, 120), (20, 20, 22))
    dd = ImageDraw.Draw(bar)
    fnt = _font(26)
    dd.text((14, 8), title, fill=(255, 255, 255), font=fnt)
    for i, x in enumerate(viol[:3]):
        dd.text((14, 42 + i * 26), f"[{x['rule']}] {x['what']}"[:70], fill=(255, 120, 120), font=_font(22))
    sheet = Image.new("RGB", (im.width, im.height + 120))
    sheet.paste(bar, (0, 0))
    sheet.paste(im, (0, 120))
    return sheet


def run(video, start=0.0, end=None, step=0.5, prof="xhs_3x4", srt=None, out_dir=".", max_shots=12, empty_thr=0.62, tag="pixel_qa", exempt=None):
    """exempt: [(t0, t1)] windows skipped entirely (e.g. full-screen transitions of an engine build)"""
    info = video_info(video)
    W, H, fps = info["w"], info["h"], info["fps"]
    end = min(end or info["duration"], info["duration"])
    frames = sorted({min(info["frames"] - 1, round(t * fps)) for t in np.arange(start, end, step)})
    frames = [n for n in frames if not any(a <= n / fps < b for a, b in (exempt or []))]
    Z = profile(prof, W, H)
    caps = read_srt(srt) if srt else []
    V = analyze(video, frames, faces=True, text=True, rects=True)
    imgs = decode_frames(video, frames, W, H)
    viol, per_frame, samples = [], {}, []
    for f in V["frames"]:
        n = f["n"]
        t = n / fps
        faces, texts, cards = frame_elements(f, W, H, caps)
        samples.append(((n, t), texts))
        vv = check_frame(n, t, imgs[n], faces, texts, cards, Z, empty_thr)
        per_frame[n] = (faces, texts, cards, vv)
        viol += vv
    tp = persistent_top(samples, Z, [n / fps for n in frames])
    viol += tp
    for x in tp:
        per_frame[x["n"]][3].append(x)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # screenshots: first hit of every rule, then more hits round-robin (a frame may serve several rules)
    shots, used = [], set()
    queues = {r: [x for x in viol if x["rule"] == r] for r in RULES}
    while len(shots) < max_shots and any(queues.values()):
        for r in RULES:
            while queues[r] and len(shots) < max_shots:
                x = queues[r].pop(0)
                if (r, x["n"]) in used or any(u[1] == x["n"] for u in used if u[0] == r):
                    continue
                if len([u for u in used if u[0] == r]) and any(abs(u[1] - x["n"]) < 2 * fps for u in used if u[0] == r):
                    continue                          # spread shots of one rule over time
                used.add((r, x["n"]))
                faces, texts, cards, vv = per_frame[x["n"]]
                p = out_dir / f"{tag}_{r}_f{x['n']:05d}.png"
                annotate(imgs[x["n"]], Z, faces, texts, cards, [y for y in vv if y["rule"] == r] + [y for y in vv if y["rule"] != r],
                         f"{Path(video).name}  frame {x['n']}  t={x['t']:.2f}s  [{r}]").save(p)
                shots.append(str(p))
                break
    summary = {r: {"hits": sum(1 for x in viol if x["rule"] == r), "frames": len({x["n"] for x in viol if x["rule"] == r})} for r in RULES}
    rep = {
        "tool": "qa.pixel_qa", "video": str(video), "window_s": [start, round(end, 3)], "step_s": step, "sampled_frames": len(frames),
        "profile": prof, "zones_px": {"caption_band": rnd(Z["caption_band"]), "top_band": rnd(Z["top_band"]), "mouth": "lower third of each face box"},
        "captions_srt": srt, "caption_lines_known": len(caps), "exempt_windows_s": exempt or [],
        "gate": "FAIL" if viol else "PASS", "summary": summary, "screenshots": shots,
        "violations": viol,
    }
    save_json(out_dir / f"{tag}_report.json", rep)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float)
    ap.add_argument("--step", type=float, default=0.5)
    ap.add_argument("--profile", default="xhs_3x4")
    ap.add_argument("--srt")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--tag", default="pixel_qa")
    a = ap.parse_args()
    rep = run(a.video, a.start, a.end, a.step, a.profile, a.srt, a.out_dir, tag=a.tag)
    print(json.dumps({k: rep[k] for k in ("gate", "sampled_frames", "summary", "screenshots")}, ensure_ascii=False, indent=1))
    sys.exit(0 if rep["gate"] == "PASS" else 1)


if __name__ == "__main__":
    main()
