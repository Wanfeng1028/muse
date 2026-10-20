"""xiaolu-motion command line.

  python3 -m render build    STORYBOARD [--out-dir DIR] [--formats prores,hevc] [--workers 4] [--selftest]
  python3 -m render resolve  STORYBOARD [--out RESOLVED]
  python3 -m render overlay  RESOLVED --out OVERLAY.mov [--layer front|behind|invert] [--formats prores,hevc] [--workers 4]
  python3 -m render composite RESOLVED --front F.mov [--behind B.mov] [--invert I.mov] --out FINAL.mp4
  python3 -m render stills   RESOLVED --times 1.0 2.5 --out-dir DIR [--mode overlay|opaque] [--style NAME]

`build` = resolve -> overlay layers behind / front / invert (ProRes 4444, optional HEVC-alpha; empty
layers are skipped) -> composite -> QA gate
(qa.check exact boxes + qa.pixel_qa on the final) -> contact sheets. QA is a gate: on any
hit the MP4 is renamed final.QA_FAILED.mp4, BUILD_STATUS.json says FAIL and the exit code is 1.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from .common import load_json, load_style, save_json


def cmd_resolve(a):
    from timeline.resolve import resolve
    res, rep = resolve(a.storyboard)
    print(json.dumps(rep.dump(), ensure_ascii=False, indent=1))
    if not rep.ok:
        sys.exit(1)
    out = a.out or str(Path(a.storyboard).with_suffix("")) + ".resolved.json"
    save_json(out, res)
    print("wrote", out)


def cmd_overlay(a):
    from .overlay import render_overlay
    st = render_overlay(a.resolved, a.out, a.workers, tuple(a.formats.split(",")), layer=a.layer)
    print(json.dumps(st and {k: st[k] for k in ("frames", "wall_render_s", "per_frame_ms", "outputs", "bytes")}, indent=1))


def cmd_composite(a):
    from .composite import composite
    print(composite(a.resolved, {"front": a.front, "behind": a.behind, "invert": a.invert}, a.out))


def cmd_stills(a):
    import numpy as np
    from PIL import Image
    from .overlay import stills
    res = load_json(a.resolved)
    tok = load_style(a.style) if a.style else None
    ims, info = stills(res, a.times, mode=a.mode, tokens=tok)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for t, im in zip(a.times, ims):
        Image.fromarray(im, "RGBA").save(out / f"still_{t:07.3f}.png")
    print("wrote", len(ims), "stills to", out)


def _ensure_words(sb_path):
    """examples keep only paths: build words.json from the sources file when it is missing"""
    sb = load_json(sb_path)
    if not sb.get("words"):
        return
    wp = (Path(sb_path).parent / sb["words"]).resolve()
    src = Path(sb_path).parent / "sources.json"
    if wp.exists() or not src.exists():
        return
    import subprocess
    S = load_json(src)["words"]
    cmd = [sys.executable, "-m", "timeline.words", "--whisper", S["whisper"], "--media", S["media"], "--out", str(wp)]
    if S.get("compiled"):
        cmd += ["--compiled", S["compiled"]]
    subprocess.run(cmd, check=True)


def cmd_build(a):
    from timeline.resolve import resolve
    from qa import check, contact_sheet, pixel_qa
    from .composite import composite
    from .fonts import missing_open_fonts
    from .overlay import render_overlay
    T = {}
    t0 = time.time()
    sb = Path(a.storyboard)
    out = Path(a.out_dir or sb.parent / "out")
    out.mkdir(parents=True, exist_ok=True)
    _ensure_words(sb)
    res, rep = resolve(sb)
    save_json(out / "resolve_report.json", rep.dump())
    if not rep.ok:
        print(json.dumps(rep.dump(), ensure_ascii=False, indent=1))
        save_json(out / "BUILD_STATUS.json", {"status": "FAIL", "stage": "resolve", "errors": rep.errors})
        sys.exit(1)
    rp = save_json(out / "storyboard.resolved.json", res)
    T["resolve_s"] = round(time.time() - t0, 2)
    formats = tuple(a.formats.split(","))
    layers, stats = {}, {}
    for layer in ("behind", "front", "invert"):
        tl = time.time()
        st = render_overlay(res, out / f"overlay_{layer}.mov", a.workers, formats, layer=layer, verbose=False)
        if st:
            layers[layer] = str(out / f"overlay_{layer}.mov")
            stats[layer] = st
            T[f"overlay_{layer}_s"] = round(time.time() - tl, 2)
    tc = time.time()
    pending = out / "final.pending.mp4"
    comp = composite(res, layers, pending)
    T["composite_s"] = round(time.time() - tc, 2)
    tq = time.time()
    qa_dir = out / "qa"
    q1 = check.run(rp, final=pending, out_dir=qa_dir)
    ex = [(t["t0"], t["t1"]) for t in res["transitions"]]
    q2 = pixel_qa.run(pending, step=0.5, prof=q1["profile"], out_dir=qa_dir, tag="pixel_final", exempt=ex)
    T["qa_s"] = round(time.time() - tq, 2)
    ok = q1["gate"] == "PASS" and q2["gate"] == "PASS"
    final = out / ("final.mp4" if ok else "final.QA_FAILED.mp4")
    pending.replace(final)
    sheets = {}
    if "front" in layers:
        ts = time.time()
        sheets["contact_sheet"] = contact_sheet.sheet(rp, layers["front"], final, out / "contact_sheet.png")["out"]
        sheets["edges"] = contact_sheet.edges(rp, layers["front"], final, out / "contact_edges.png")["out"]
        T["sheets_s"] = round(time.time() - ts, 2)
    if a.selftest:
        from qa import alpha_selftest, camera_selftest
        if "front" in layers:
            st = alpha_selftest.run(rp, layers["front"])
            save_json(qa_dir / "alpha_selftest.json", st)
            sheets["alpha_selftest"] = {"pass": st["pass"], "file": str(qa_dir / "alpha_selftest.json")}
        bo = out / "base_only.mp4"
        composite(res, None, bo)
        cs = camera_selftest.run(rp, bo)
        save_json(qa_dir / "camera_selftest.json", cs)
        sheets["camera_selftest"] = {"pass": cs["pass"], "file": str(qa_dir / "camera_selftest.json")}
    T["total_s"] = round(time.time() - t0, 2)
    status = {
        "status": "PASS" if ok else "FAIL", "final": str(final), "overlays": layers,
        "hevc_alpha": {k: v["outputs"].get("hevc_alpha") for k, v in stats.items()},
        "qa": {"bbox_gate": q1["gate"], "bbox_summary": {k: v["hits"] for k, v in q1["summary"].items()},
               "pixel_gate": q2["gate"], "pixel_summary": {k: v["hits"] for k, v in q2["summary"].items()},
               "reports": [str(qa_dir / "qa_report.json"), str(qa_dir / "pixel_final_report.json")]},
        "fonts_missing_open": missing_open_fonts(res["tokens"]), "timing_s": T,
        "render_stats": {k: {x: v[x] for x in ("frames", "wall_render_s", "per_frame_ms", "subframes_per_frame", "bytes")} for k, v in stats.items()},
        "sheets": sheets,
    }
    save_json(out / "BUILD_STATUS.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=1))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(prog="python3 -m render")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("resolve"); s.add_argument("storyboard"); s.add_argument("--out"); s.set_defaults(fn=cmd_resolve)
    s = sp.add_parser("overlay"); s.add_argument("resolved"); s.add_argument("--out", required=True); s.add_argument("--layer", choices=["front", "behind", "invert"])
    s.add_argument("--formats", default="prores"); s.add_argument("--workers", type=int, default=4); s.set_defaults(fn=cmd_overlay)
    s = sp.add_parser("composite"); s.add_argument("resolved"); s.add_argument("--front"); s.add_argument("--behind"); s.add_argument("--invert"); s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_composite)
    s = sp.add_parser("stills"); s.add_argument("resolved"); s.add_argument("--times", type=float, nargs="+", required=True); s.add_argument("--out-dir", required=True)
    s.add_argument("--mode", default="overlay", choices=["overlay", "opaque"]); s.add_argument("--style"); s.set_defaults(fn=cmd_stills)
    s = sp.add_parser("build"); s.add_argument("storyboard"); s.add_argument("--out-dir"); s.add_argument("--formats", default="prores,hevc")
    s.add_argument("--workers", type=int, default=4); s.add_argument("--selftest", action="store_true"); s.set_defaults(fn=cmd_build)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
