"""Reel covers: a sharp still of a reel frame (rendered from the 4K source through that frame's
camera window, not grabbed from the compressed reel) with the SETTLED headline of each variant
composited at the same centre the reel uses. One cover per headline variant.

Stage 1, candidates:
  python3 reel_cover.py cands <edit_dir> <kind> <overlay_dir> <out_dir> [step] [a-b,c-d]
  Every <step>th reel frame (default 8) whose padded face box sits inside the centred 3:4 grid
  window (1080x1440 at y 240 to 1680) and clear of the headline box is rendered to
  <out_dir>/cands/c_<frame>.png, screened with the expression gate
  (face-screen.swift: both eyes open, mouth closed or deliberate, facing the lens) and listed in
  <out_dir>/cands.json; <out_dir>/cands_pass.png is a contact sheet of the PASS frames.
Stage 2, compose:
  python3 reel_cover.py compose <edit_dir> <kind> <overlay_dir> <out_dir> <frame> <name> [headline_cy]
  Writes <out_dir>/<name>-h<k>-cover.png and .jpg (1080x1920) per variant, and
  <out_dir>/<name>-covers-grid-check.png: each cover beside its centred 3:4 crop (what the
  Instagram profile grid shows), so the whole headline and the speaker's face can be checked in the crop.
The headline PNGs come from overlay_build.py (<overlay_dir>/headline_h<k>_settled_2x.png); the
headline centre and the face boxes from <overlay_dir>/audit.json and overlay_geom.py.
"""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from overlay_geom import geom, overlap  # noqa: E402

FACE_SCREEN = Path(__file__).parent / "face-screen"  # compiled from face-screen.swift by setup.sh


def grade_vf(props):
    """The house grade (grade.py) on a 4K still: the same .cube the Node renderers apply, through lut3d."""
    g = props.get("grade")
    return (f"scale=in_range=tv:in_color_matrix=bt709:out_range=pc:flags=accurate_rnd+full_chroma_int,format=gbrpf32le,"
            f"lut3d=file={g}:interp=tetrahedral,format=rgb24") if g else None
FPS = 24000 / 1001
GRID = (0, 240, 1080, 1680)  # the centred 3:4 window of a 1080x1920 cover
HM = 26  # overlay_build.py's margin around the headline panel inside the settled PNG
AIR = 24


def still(props, f, path):
    """Reel frame f rendered from the source: exact source frame, camera window, Lanczos."""
    seg = next(s for s in props["segments"] if s["outFrame"] <= f < s["outFrame"] + s["frames"])
    sf = seg["srcFrame"] + (f - seg["outFrame"])
    tmp = path.with_suffix(".src.png")
    gv = grade_vf(props)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{(sf - 0.25) / FPS:.6f}", "-i", props["src"],
                    "-map", "0:v:0", "-frames:v", "1"] + (["-vf", gv] if gv else []) + [str(tmp)], check=True)
    x0, y0, w = props["camera"][f]
    h = w * props["outH"] / props["outW"]
    im = Image.open(tmp).convert("RGB").resize((props["outW"], props["outH"]), Image.LANCZOS, box=(x0, y0, x0 + w, y0 + h))
    tmp.unlink()
    im.save(path)
    return im


def stills(props, frames, d):
    """Many reel frames at once: each reel segment is decoded ONCE (a long GOP source makes a
    seek per frame slow) and only the wanted frames are kept, cropped and resized."""
    want = sorted(set(frames))
    out = {}
    for seg in props["segments"]:
        fs = [f for f in want if seg["outFrame"] <= f < seg["outFrame"] + seg["frames"] and not (d / f"c_{f:05d}.png").exists()]
        if not fs:
            continue
        tmp = d / "_src"
        tmp.mkdir(exist_ok=True)
        expr = "+".join(f"eq(n\\,{f - seg['outFrame']})" for f in fs)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{(seg['srcFrame'] - 0.25) / FPS:.6f}", "-i", props["src"],
                        "-map", "0:v:0", "-frames:v", str(len(fs)), "-vf", f"select={expr}" + (f",{grade_vf(props)}" if grade_vf(props) else ""), "-fps_mode", "passthrough",
                        "-q:v", "1", str(tmp / "s_%04d.jpg")], check=True)
        got = sorted(tmp.glob("s_*.jpg"))
        assert len(got) == len(fs), (len(got), len(fs))
        for f, g in zip(fs, got):
            x0, y0, w = props["camera"][f]
            h = w * props["outH"] / props["outW"]
            Image.open(g).convert("RGB").resize((props["outW"], props["outH"]), Image.LANCZOS, box=(x0, y0, x0 + w, y0 + h)).save(d / f"c_{f:05d}.png")
            g.unlink()
        tmp.rmdir()
    return {f: d / f"c_{f:05d}.png" for f in want}


def head_box(audit, ow):
    cx, cy = audit["headline_pos"]
    w = max(h["w"] for h in audit["headlines"])
    hh = max(h["h"] for h in audit["headlines"])
    return [cx - w / 2, cy - hh / 2, cx + w / 2, cy + hh / 2]


def main():
    mode, E, kind, ovd, out = sys.argv[1], Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5])
    if not FACE_SCREEN.exists():
        raise SystemExit(f"{FACE_SCREEN} is missing: run scripts/setup.sh once")
    out.mkdir(parents=True, exist_ok=True)
    props = json.load(open(E / f"reel/props_reel_{kind}_abs.json"))
    audit = json.load(open(ovd / "audit.json"))
    HB = head_box(audit, props["outW"])
    if mode == "cands":
        step = int(sys.argv[6]) if len(sys.argv) > 6 else 8
        ranges = [tuple(int(x) for x in r.split("-")) for r in sys.argv[7].split(",")] if len(sys.argv) > 7 else None
        G = geom(E, kind)["frames"]
        if ranges:  # a denser pass over chosen frame ranges ("a-b,c-d", inclusive)
            G = [e for e in G if any(a <= e["f"] <= b for a, b in ranges)]
        d = out / "cands"
        # candidates are keyed on the reel plan: a re-planned reel (new props) invalidates the old stills
        pf = E / f"reel/props_reel_{kind}_abs.json"
        if (out / "cands.json").exists() and pf.stat().st_mtime > (out / "cands.json").stat().st_mtime:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
            (out / "cands.json").unlink()
            print("reel plan changed since the last candidate pass: old candidates cleared")
        d.mkdir(exist_ok=True)
        picks = []
        for e in G[::step]:
            fc = e["face"]
            if not fc:
                continue
            if fc[0] < GRID[0] + 20 or fc[2] > GRID[2] - 20 or fc[1] < GRID[1] + 20 or fc[3] > GRID[3] - 20:
                continue
            if overlap([HB[0] - AIR, HB[1] - AIR, HB[2] + AIR, HB[3] + AIR], fc) > 0:
                continue
            picks.append(e)
        got = stills(props, [e["f"] for e in picks], d)
        paths = [got[e["f"]] for e in picks]
        res = subprocess.run([str(FACE_SCREEN)] + [str(p) for p in paths], capture_output=True, text=True)
        lines = res.stdout.splitlines()
        rows = []
        for e, p in zip(picks, paths):
            ln = next((l for l in lines if p.name in l), "")
            rows.append({"frame": e["f"], "t": round(e["f"] / FPS, 2), "face": e["face"], "targets": e["target_names"],
                         "pass": " PASS" in ln or ln.rstrip().endswith("PASS"), "screen": ln.strip()})
        if (out / "cands.json").exists():
            old = {r["frame"]: r for r in json.load(open(out / "cands.json"))["rows"]}
            old.update({r["frame"]: r for r in rows})
            rows = [old[k] for k in sorted(old)]
        json.dump({"headline_box": HB, "grid": GRID, "rows": rows}, open(out / "cands.json", "w"), indent=1)
        ok = [r for r in rows if r["pass"]]
        print(f"{len(rows)} candidates inside the 3:4 window and clear of the headline, {len(ok)} PASS the expression gate")
        for r in rows:
            print(f"  f{r['frame']:5d} {r['t']:6.2f}s {'PASS' if r['pass'] else 'rej '} {r['targets']} | {r['screen'][-110:]}")
        if ok:
            tw, th = 216, 384
            cols = min(8, len(ok))
            S = Image.new("RGB", (tw * cols, th * ((len(ok) + cols - 1) // cols)))
            for i, r in enumerate(ok):
                im = Image.open(d / f"c_{r['frame']:05d}.png").resize((tw, th))
                ImageDraw.Draw(im).text((4, 4), f"f{r['frame']}", fill=(255, 255, 0))
                S.paste(im, (tw * (i % cols), th * (i // cols)))
            S.save(out / "cands_pass.png")
    elif mode == "compose":
        f, name = int(sys.argv[6]), sys.argv[7]
        # optional: a different headline centre y for the cover (the reel's own centre by default),
        # e.g. to keep a board item clear; it must still sit inside the 3:4 grid window
        hy = float(sys.argv[8]) if len(sys.argv) > 8 else None
        base = still(props, f, out / f"{name}-cover-frame.png")
        covers = []
        for k, h in enumerate(audit["headlines"], 1):
            S2 = Image.open(ovd / f"headline_h{k}_settled_2x.png").convert("RGBA")
            sx = S2.width / (h["w"] + 2 * HM)
            S1 = S2.resize((round(S2.width / sx), round(S2.height / sx)), Image.LANCZOS)
            cx, cy = audit["headline_pos"]
            if hy is not None:
                cy = hy
            top, bot = cy - S1.height / 2 + HM, cy + S1.height / 2 - HM
            assert GRID[1] <= top and bot <= GRID[3], f"headline {top:.0f} to {bot:.0f} leaves the 3:4 window"
            im = base.convert("RGBA")
            im.alpha_composite(S1, (round(cx - S1.width / 2), round(cy - S1.height / 2)))
            im = im.convert("RGB")
            im.save(out / f"{name}-h{k}-cover.png")
            im.save(out / f"{name}-h{k}-cover.jpg", quality=95, subsampling=0)
            covers.append(im)
        # grid check: each cover beside its centred 3:4 crop
        tw = 360
        th = round(tw * 1920 / 1080)
        gh = round(tw * 1440 / 1080)
        C = Image.new("RGB", ((tw * 2 + 30) * len(covers), th + 40), (24, 24, 24))
        dr = ImageDraw.Draw(C)
        for i, im in enumerate(covers):
            x = (tw * 2 + 30) * i
            full = im.resize((tw, th))
            ImageDraw.Draw(full).rectangle([0, round(240 * tw / 1080), tw - 1, round(1680 * tw / 1080)], outline=(255, 210, 0), width=2)
            C.paste(full, (x, 40))
            C.paste(im.crop(GRID).resize((tw, gh)), (x + tw + 10, 40 + (th - gh) // 2))
            dr.text((x + 4, 8), f"H{i + 1} cover (yellow = 3:4 grid window) | grid crop", fill=(255, 255, 255))
        C.save(out / f"{name}-covers-grid-check.png")
        r = subprocess.run([str(FACE_SCREEN), str(out / f"{name}-cover-frame.png")], capture_output=True, text=True)
        print(r.stdout.strip())
        print(f"covers for frame {f}: " + ", ".join(f"{name}-h{k}-cover.jpg" for k in range(1, len(covers) + 1)))


if __name__ == "__main__":
    main()
