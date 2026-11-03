"""Render gate for storyboards built with this engine (exact component bboxes).

  python3 -m qa.check resolved.json [--final final.mp4] --out-dir DIR

Every frame (qa.sample_every, default 1) the page reports each active component's boxes
(XM.bboxes(t)); the base footage's faces come from Apple Vision on the source frames and
are carried through the same cover-fit + camera maths as the compositor (render/camera.py).
Gate rules — any hit fails the render:
  face_cover    overlay box intersects a face box
  mouth_cover   overlay box intersects the mouth zone (lower third of the face box)
  caption_band  overlay box intersects the caption band (74–86 % of the height)
  overlap       boxes of two different shots intersect (transitions exempt: full-screen by design)
  safe_zone     box outside the profile's safe rectangle (bleed boxes exempt)
  min_font      text smaller than the profile minimum
  transition_cover  a transition does not cover the whole frame at its midpoint
Writes DIR/qa_report.json and annotated PNGs of the first frame of every problem.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from render.camera import to_canvas, window
from render.common import load_json, save_json, video_info
from render.overlay import bboxes as page_bboxes
from .pixel_qa import _font
from .vision import analyze
from .zones import area, inter, mouth_zone, outside, pad, profile, rnd

GATE_RULES = ["face_cover", "mouth_cover", "caption_band", "overlap", "safe_zone", "min_font", "transition_cover"]


def _cover_map(sw, sh, W, H):
    s = max(W / sw, H / sh)
    w2, h2 = max(W, 2 * round(sw * s / 2)), max(H, 2 * round(sh * s / 2))
    return w2 / sw, h2 / sh, (w2 - W) / 2, (h2 - H) / 2


def base_faces(res, frames):
    """timeline frame -> [{"box", "mouth_zone"}] in canvas px (after cover fit + camera)"""
    C = res["canvas"]
    W, H, FPS = C["w"], C["h"], C["fps"]
    need = {}
    for n in frames:
        t = n / FPS
        c = next((c for c in res["base"] if c["t0"] - 1e-9 <= t < c["t1"]), None)
        if not c:
            continue
        info = c.get("src_info") or video_info(c["src"])
        m = round((c["in"] + t - c["t0"]) * info["fps"])
        need.setdefault(c["src"], {})[n] = (m, c, info)
    out = {}
    for src, mp in need.items():
        V = analyze(src, [m for m, _, _ in mp.values()], faces=True)
        by_m = {f["n"]: f.get("faces", []) for f in V["frames"]}
        for n, (m, c, info) in mp.items():
            sx, sy, ox, oy = _cover_map(info["w"], info["h"], W, H)
            win = window(c["camera"], n / FPS, W, H)
            fl = []
            for fc in by_m.get(m, []):
                b = fc["box"]
                x0, y0 = to_canvas(win, b["x"] * sx - ox, b["y"] * sy - oy)
                x1, y1 = to_canvas(win, (b["x"] + b["w"]) * sx - ox, (b["y"] + b["h"]) * sy - oy)
                box = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
                fl.append({"box": box, "mouth_zone": mouth_zone(box)})
            out[n] = fl
    return out


def grab_frames(video, frames, W, H):
    sel = "+".join(f"eq(n\\,{n})" for n in frames)
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"select='{sel}'", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True)
    arr = np.frombuffer(r.stdout, np.uint8)
    return {n: arr[i * W * H * 3:(i + 1) * W * H * 3].reshape(H, W, 3) for i, n in enumerate(frames[:arr.size // (W * H * 3)])}


def draw(img, Z, boxes, faces, hits, title):
    im = Image.fromarray(img).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    b = Z["caption_band"]
    d.rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], fill=(255, 210, 0, 55), outline=(255, 190, 0, 255), width=3)
    s = Z["safe"]
    d.rectangle([s["x"], s["y"], s["x"] + s["w"], s["y"] + s["h"]], outline=(255, 255, 255, 160), width=2)
    for f in faces:
        fb, mz = f["box"], f["mouth_zone"]
        d.rectangle([fb["x"], fb["y"], fb["x"] + fb["w"], fb["y"] + fb["h"]], outline=(40, 140, 255, 255), width=4)
        d.rectangle([mz["x"], mz["y"], mz["x"] + mz["w"], mz["y"] + mz["h"]], fill=(255, 0, 200, 50), outline=(255, 0, 200, 255), width=2)
    bad = {(h["item"], h["label"]) for h in hits}
    for x in boxes:
        col = (255, 40, 40, 255) if (x["item"], x["label"]) in bad else (0, 220, 120, 230)
        d.rectangle([x["x"], x["y"], x["x"] + x["w"], x["y"] + x["h"]], outline=col, width=5 if col[0] == 255 else 2)
    im = Image.alpha_composite(im, ov).convert("RGB")
    bar = Image.new("RGB", (im.width, 90), (20, 20, 22))
    dd = ImageDraw.Draw(bar)
    dd.text((12, 6), title, fill=(255, 255, 255), font=_font(22))
    for i, h in enumerate(hits[:4]):
        dd.text((12, 32 + i * 14), f"[{h['rule']}] {h['msg']}"[:110], fill=(255, 130, 130), font=_font(13))
    sheet = Image.new("RGB", (im.width, im.height + 90))
    sheet.paste(bar, (0, 0))
    sheet.paste(im, (0, 90))
    return sheet


def run(res_path, final=None, out_dir=".", overlay=None):
    res = load_json(res_path)
    C = res["canvas"]
    W, H, FPS, N = C["w"], C["h"], C["fps"], res["frames"]
    q = res.get("qa", {})
    Z = profile(q.get("safe_zone", "xhs_3x4" if H == 1440 else "xhs_9x16"), W, H, q.get("captions"))
    avoid = set(q.get("avoid", ["face", "captions"]))
    tol = float(q.get("overlap_tolerance_px", 0.0))
    min_font = q.get("min_font_px", Z["min_font_px"])
    step = int(q.get("sample_every", 1))
    frames = list(range(0, N, step))
    B = page_bboxes(res, [n / FPS for n in frames])
    faces = base_faces(res, frames) if "face" in avoid else {}
    hits = []

    def hit(rule, n, box, msg, **extra):
        hits.append({"rule": rule, "n": n, "t": round(n / FPS, 4), "item": box.get("item"), "label": box.get("label"), "box": rnd(box), "msg": msg, **extra})
    for n, boxes in zip(frames, B):
        vis = [b for b in boxes if b["alpha"] >= 0.05 and b["w"] > 0 and b["h"] > 0]
        normal = [b for b in vis if b["role"] != "transition"]
        for b in normal:
            if "face" in avoid:
                for f in faces.get(n, []):
                    fb = pad(f["box"], Z["face_pad"])
                    if inter(b, fb) > 0:
                        hit("face_cover", n, b, f"{b['item']} '{b['label']}' over the face", face=rnd(fb))
                    if inter(b, f["mouth_zone"]) > 0:
                        hit("mouth_cover", n, b, f"{b['item']} '{b['label']}' in the mouth zone", mouth=rnd(f["mouth_zone"]))
            if "captions" in avoid and inter(b, Z["caption_band"]) > 0:
                hit("caption_band", n, b, f"{b['item']} '{b['label']}' in the caption band")
            if not b["bleed"] and outside(b, Z["safe"]):
                hit("safe_zone", n, b, f"{b['item']} '{b['label']}' outside the safe area")
            if b["kind"] == "text" and b["font_px"] and b["font_px"] < min_font:
                hit("min_font", n, b, f"{b['item']} '{b['label']}' {b['font_px']}px < {min_font}px")
        for i, a in enumerate(normal):
            for b in normal[i + 1:]:
                if a["item"] != b["item"] and inter(a, b) > tol:
                    hit("overlap", n, a, f"{a['item']} '{a['label']}' overlaps {b['item']} '{b['label']}'", other=rnd(b))
    # transitions must fully cover the frame at their midpoint (that is where the base cut hides)
    tmid = [round(tr["at"] * FPS) for tr in res["transitions"] if tr.get("type")]
    if tmid:
        TB = page_bboxes(res, [m / FPS for m in tmid])
        for tr, m, boxes in zip(res["transitions"], tmid, TB):
            full = any(b["item"] == tr["id"] and b["full"] for b in boxes)
            if not full:
                hits.append({"rule": "transition_cover", "n": m, "t": round(m / FPS, 4), "item": tr["id"], "label": "", "box": {}, "msg": f"{tr['id']} does not cover the frame at its midpoint"})
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = []
    src = final or overlay
    if hits and src:
        firsts = {}
        for h in hits:
            firsts.setdefault((h["rule"], h["item"]), h["n"])
        want = sorted(set(firsts.values()))[:12]
        imgs = grab_frames(src, want, W, H)
        for n in want:
            hh = [h for h in hits if h["n"] == n]
            p = out_dir / f"qa_f{n:05d}.png"
            draw(imgs[n], Z, B[frames.index(n)] if n in frames else [], faces.get(n, []), hh, f"frame {n}  t={n / FPS:.3f}s  {len(hh)} hit(s)").save(p)
            shots.append(str(p))
    summary = {r: {"hits": sum(1 for h in hits if h["rule"] == r), "frames": len({h["n"] for h in hits if h["rule"] == r})} for r in GATE_RULES}
    face_frames = sum(1 for n in frames if faces.get(n))
    rep = {"tool": "qa.check", "resolved": str(res_path), "frames_checked": len(frames), "profile": Z["name"],
           "zones_px": {"caption_band": rnd(Z["caption_band"]), "safe": rnd(Z["safe"]), "mouth": "lower third of each face box", "min_font_px": min_font},
           "faces": {"frames_with_face": face_frames, "source": "Apple Vision on base source frames -> cover fit -> camera"},
           "boxes_checked": sum(len(b) for b in B), "gate": "FAIL" if hits else "PASS", "summary": summary, "screenshots": shots,
           "violations": hits[:500], "violations_total": len(hits)}
    save_json(out_dir / "qa_report.json", rep)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("resolved")
    ap.add_argument("--final")
    ap.add_argument("--overlay")
    ap.add_argument("--out-dir", default=".")
    a = ap.parse_args()
    rep = run(a.resolved, a.final, a.out_dir, a.overlay)
    print(json.dumps({k: rep[k] for k in ("gate", "frames_checked", "boxes_checked", "faces", "summary", "screenshots")}, ensure_ascii=False, indent=1))
    sys.exit(0 if rep["gate"] == "PASS" else 1)


if __name__ == "__main__":
    main()
