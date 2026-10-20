"""Contact sheets: sample a video at a fixed rate and tile labelled thumbnails.

Default mode tiles frames at a fixed rate. Boundary mode (--boundaries) instead reads the events of a
segments.json written by scripts/segments.py and tiles ONE sheet whose rows are the boundaries; each row shows
the frame just before the boundary, the frame in the middle of the transition, and the frame after it, so a
short blur swap or a muddy double exposure cannot fall between two samples of a fixed-rate sheet.

Row frames (all offsets are flags; times are clamped to the video and rounded to the nearest frame):
    before  = boundary - --b-pre  (default 0.10 s)
    middle  = the span's midpoint when the event has kind "span" (a montage: before = span start - b-pre,
              after = span end + b-post); otherwise boundary + --b-mid (default 0.05 s)
    after   = boundary + --b-post (default 0.30 s)
where a single transition's boundary is the event's "t" (the centre of segments.py's coverage peak, resolution
about 1 frame for cuts and half the transition length for fades).

What it cannot determine: whether the boundary is a new section or a push-in / modal inside one (segments.py
cannot either - read the row); a fade longer than 2 x b-pre puts the "before" frame inside the fade. The
sidecar boundary_sheet.json lists the exact frame indices used.

Usage:
    python -X utf8 scripts/sheets.py <video> --out <dir> [--fps 10 --cols 6 --rows 4 --thumb 300]
    python -X utf8 scripts/sheets.py <video> --out <dir> --boundaries <segments.json> [--b-pre 0.1 --b-mid 0.05 --b-post 0.3]
    python -X utf8 scripts/sheets.py --selftest
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))



def _font(size=16):
    """Label font: Arial on Windows, DejaVu on Linux, PIL's built-in bitmap font otherwise."""
    for name in ("arial.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()

def fixed_rate_sheets(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    font = _font(16)
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vf", f"fps={a.fps}",
                        str(Path(td) / "f_%04d.png")], check=True)
        frames = sorted(Path(td).glob("f_*.png"))
        per = a.cols * a.rows
        for s in range(0, len(frames), per):
            batch = frames[s:s + per]
            with Image.open(batch[0]) as im0:  # close handles: Windows cannot delete open files
                th = int(im0.height * a.thumb / im0.width)
            sheet = Image.new("RGB", (a.cols * a.thumb, a.rows * (th + 20)), "white")
            d = ImageDraw.Draw(sheet)
            for i, f in enumerate(batch):
                idx = s + i
                with Image.open(f) as src:
                    im = src.convert("RGB").resize((a.thumb, th))
                x, y = (i % a.cols) * a.thumb, (i // a.cols) * (th + 20)
                sheet.paste(im, (x, y + 20))
                d.text((x + 4, y + 1), f"#{idx} t={idx / a.fps:.2f}s", fill="black", font=font)
            sheet.save(out / f"sheet_{s // per:02d}.png")
    print(f"{len(frames)} frames -> {out}")


# ---------- boundary mode ----------
def boundary_rows(events, fps, n_frames, pre=0.10, mid=0.05, post=0.30):
    """One row per event: [(role, requested_t, frame_index), ...] for before / middle / after."""
    last = (n_frames - 1) / fps
    rows = []
    for k, e in enumerate(events):
        if e.get("kind") == "span":
            b, m, af = e["start"], (e["start"] + e["end"]) / 2, e["end"] + post
            kind = "span"
        else:
            b = e["t"]
            m, af = b + mid, b + post
            kind = "transition"
        want = [("before", b - pre), ("middle", m), ("after", af)]
        row = []
        for role, t in want:
            tc = min(max(t, 0.0), last)
            fi = int(round(tc * fps))
            row.append({"role": role, "t": round(fi / fps, 3), "requested_t": round(t, 3),
                        "clamped": abs(tc - t) > 1e-9, "frame": fi})
        rows.append({"boundary": k, "kind": kind, "t": round(b, 3), "frames": row})
    return rows


GRAB_CHUNK = 40  # one select expression of ~150 eq() terms made ffmpeg exit -12 (C32, 49 boundaries, 2026-10-04)


def grab_frames(video, indices, td, chunk=GRAB_CHUNK):
    """Decode the frames with these indices, `chunk` indices per ffmpeg pass; returns {index: path}."""
    idx = sorted(set(indices))
    out = {}
    for c0 in range(0, len(idx), chunk):
        part = idx[c0:c0 + chunk]
        expr = "+".join(f"eq(n,{i})" for i in part)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"select='{expr}'",
                        "-fps_mode", "passthrough", str(Path(td) / f"g{c0:05d}_%05d.png")], check=True)
        files = sorted(Path(td).glob(f"g{c0:05d}_*.png"))
        if len(files) != len(part):
            raise SystemExit(f"asked for {len(part)} distinct frames, decoded {len(files)} (index past the end?)")
        out.update(zip(part, files))
    return out


def boundary_sheet(video, events, out, fps=None, n_frames=None, thumb=300, pre=0.10, mid=0.05, post=0.30):
    from avio import probe
    info = probe(video)
    fps = fps or info["fps"]
    n_frames = n_frames or int(round(info["duration"] * fps))
    rows = boundary_rows(events, fps, n_frames, pre, mid, post)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    font = _font(16)
    if not rows:
        print("no boundaries in the segments file; nothing written")
        return rows
    with tempfile.TemporaryDirectory() as td:
        files = grab_frames(video, [f["frame"] for r in rows for f in r["frames"]], td)
        with Image.open(next(iter(files.values()))) as im0:
            th = int(im0.height * thumb / im0.width)
        sheet = Image.new("RGB", (3 * thumb, len(rows) * (th + 20)), "white")
        d = ImageDraw.Draw(sheet)
        for ri, r in enumerate(rows):
            for ci, f in enumerate(r["frames"]):
                with Image.open(files[f["frame"]]) as src:
                    im = src.convert("RGB").resize((thumb, th))
                x, y = ci * thumb, ri * (th + 20)
                sheet.paste(im, (x, y + 20))
                sign = {"before": -pre, "after": post}.get(f["role"])
                off = f"{sign:+.2f}" if sign is not None else ("mid" if r["kind"] == "span" else f"{mid:+.2f}")
                d.text((x + 4, y + 1), f"B{r['boundary']} {r['kind']} b={r['t']:.2f}s {f['role']} {off} "
                                       f"t={f['t']:.2f} f{f['frame']}", fill="black", font=font)
    sheet.save(out / "boundary_sheet.png")
    (out / "boundary_sheet.json").write_text(json.dumps(
        {"video": str(video), "fps": fps, "offsets": {"b_pre": pre, "b_mid": mid, "b_post": post}, "rows": rows},
        indent=1), encoding="utf-8")
    print(f"{len(rows)} boundaries x 3 frames -> {out / 'boundary_sheet.png'}")
    return rows


# ---------- calibration ----------
def _frame_arr(path):
    import numpy as np
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype=np.int16)


def selftest():
    import numpy as np
    import segments as sg
    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # positive control: a film with known boundaries (hard cut 2.5 s, crossfade 5.0 s, fade through bg 7.5 s,
        # wipe to a card 10.0 s). segments.py measures the events; the sheet must straddle them.
        sec = td / "sec.mp4"
        truth = sg.synth_sections(sec)
        res, _, fps = sg.analyse(sec, width=sg.W)
        ev = res["events"]
        rows = boundary_sheet(sec, ev, td / "pos")
        good = len(rows) == 4 and all(abs(r["t"] - t) <= 0.1 for r, t in zip(rows, truth))
        print(f"positive: 4 rows at the known boundaries {[r['t'] for r in rows]} want {truth} (+-0.1 s) "
              f"-> {'ok' if good else 'FAIL'}")
        ok &= good
        want = [(r["frames"][k]["frame"]) for r in rows for k in range(3)]
        with tempfile.TemporaryDirectory() as gd:
            fr = grab_frames(sec, want, gd)
            arr = {i: _frame_arr(p) for i, p in fr.items()}
        hl = (slice(8, 30), slice(8, 80))  # headline region: local_motion never touches it

        def head_err(frame, sec_no):
            return int(np.abs(arr[frame][hl] - sg.layout(sec_no)[hl]).max())
        cut, xf = rows[0], rows[1]
        e = [head_err(cut["frames"][0]["frame"], 0), head_err(cut["frames"][1]["frame"], 1),
             head_err(cut["frames"][2]["frame"], 1)]
        good = max(e) <= 25
        print(f"positive, hard cut at 2.5 s: headline max error vs the known layouts before/middle/after "
              f"{e} (want each <= 25: before = section 0, middle and after = section 1) -> {'ok' if good else 'FAIL'}")
        ok &= good
        e2 = head_err(xf["frames"][2]["frame"], 2)
        good = e2 <= 25
        print(f"positive, crossfade at 5.0 s: 'after' headline error vs section 2 {e2} (want <= 25) "
              f"-> {'ok' if good else 'FAIL'}")
        ok &= good
        diffs = [float(np.abs(arr[r["frames"][0]["frame"]] - arr[r["frames"][2]["frame"]]).mean()) for r in rows]
        good = all(x >= 5 for x in diffs)
        print(f"positive, before vs after mean abs diff per boundary {[round(x, 1) for x in diffs]} "
              f"(want each >= 5 grey levels) -> {'ok' if good else 'FAIL'}")
        ok &= good
        # the check must be able to fail: with a wrong offset (before = 0.3 s AFTER the cut) the same test trips
        bad = boundary_rows(ev[:1], fps, int(round(res["duration_s"] * fps)), pre=-0.3)[0]["frames"][0]["frame"]
        with tempfile.TemporaryDirectory() as gd:
            eb = int(np.abs(_frame_arr(grab_frames(sec, [bad], gd)[bad])[hl] - sg.layout(0)[hl]).max())
        good = eb > 25
        print(f"broken-offset control: 'before' frame taken after the cut, headline error vs section 0 {eb} "
              f"(want > 25, i.e. the positive check would FAIL) -> {'ok' if good else 'FAIL'}")
        ok &= good
        # negative control: a static film (no motion at all) with a boundary in it - the three frames must be identical
        stat = td / "static.mp4"
        vid = np.zeros((6 * sg.FPS, sg.H, sg.W), np.uint8)
        vid[:] = np.clip(sg.layout(0), 0, 255).astype(np.uint8)
        sg._encode(vid, stat)
        rows = boundary_sheet(stat, [{"t": 3.0, "kind": "transition", "coverage": 1.0}], td / "neg")
        with tempfile.TemporaryDirectory() as gd:
            fr = grab_frames(stat, [f["frame"] for f in rows[0]["frames"]], gd)
            a3 = [_frame_arr(fr[f["frame"]]) for f in rows[0]["frames"]]
        import hashlib
        hs = [hashlib.sha1(x.astype(np.uint8).tobytes()).hexdigest()[:8] for x in a3]
        mx = max(int(np.abs(a3[i] - a3[j]).max()) for i in range(3) for j in range(i + 1, 3))
        good = mx <= 2
        print(f"negative: boundary inside a static stretch, frame hashes {hs}, max abs diff {mx} "
              f"(want <= 2 grey levels, codec noise only) -> {'ok' if good else 'FAIL'}")
        ok &= good
        # a span (montage) event gets its own middle: before = start - pre, after = end + post
        mont = td / "mont.mp4"
        a0, a1 = sg.synth_montage(mont)
        r2 = boundary_rows([{"t": 4.5, "kind": "span", "start": a0, "end": a1}], sg.FPS, 9 * sg.FPS)[0]["frames"]
        got = [f["t"] for f in r2]
        want_t = [a0 - 0.1, (a0 + a1) / 2, a1 + 0.3]
        good = all(abs(g - w) <= 1 / sg.FPS for g, w in zip(got, want_t))
        print(f"span row: frame times {got} want {[round(x, 2) for x in want_t]} -> {'ok' if good else 'FAIL'}")
        ok &= good
        # many boundaries: 150 indices decode across chunks and each maps to its own frame (a single pass of
        # ~150 eq() terms made ffmpeg exit -12 on C32); control: a wrong pairing must read as different
        many = list(range(0, 150))
        with tempfile.TemporaryDirectory() as gd, tempfile.TemporaryDirectory() as sd:
            fr = grab_frames(mont, many, gd)
            probe_idx = [0, 41, 79, 149]
            alone = {}
            for i in probe_idx:
                sub = Path(sd) / str(i)
                sub.mkdir()
                alone[i] = _frame_arr(grab_frames(mont, [i], sub)[i])
            right = max(float(np.abs(_frame_arr(fr[i]) - alone[i]).mean()) for i in probe_idx)
            wrong = float(np.abs(_frame_arr(fr[0]) - alone[149]).mean())
        good = len(fr) == 150 and right <= 1.0 and wrong > right + 5
        print(f"150 indices in chunks of {GRAB_CHUNK}: decoded {len(fr)}, right-pair diff {right:.2f} (want <= 1), "
              f"wrong-pair diff {wrong:.2f} (want > right + 5) -> {'ok' if good else 'FAIL'}")
        ok &= good
        # default mode is untouched: a 6 s film at 2 fps, 6 cols x 4 rows = 12 frames = one sheet_00.png, 6 thumbs wide
        ns = argparse.Namespace(video=str(stat), out=str(td / "def"), fps=2.0, cols=6, rows=4, thumb=100)
        fixed_rate_sheets(ns)
        made = sorted(p.name for p in (td / "def").glob("*.png"))
        with Image.open(td / "def" / "sheet_00.png") as im:
            wd = im.width
        good = made == ["sheet_00.png"] and wd == 600
        print(f"default mode unchanged: {made}, width {wd} (want ['sheet_00.png'], 600) -> {'ok' if good else 'FAIL'}")
        ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--fps", type=float, default=10)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--thumb", type=int, default=300)
    ap.add_argument("--boundaries", help="segments.json from scripts/segments.py: one sheet, one row per boundary")
    ap.add_argument("--b-pre", type=float, default=0.10, help="seconds before the boundary (default 0.10)")
    ap.add_argument("--b-mid", type=float, default=0.05,
                    help="seconds after the boundary for the middle frame when the event has no span (default 0.05)")
    ap.add_argument("--b-post", type=float, default=0.30, help="seconds after the boundary (default 0.30)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not a.video or not a.out:
        ap.error("video and --out are required")
    if a.boundaries:
        seg = json.loads(Path(a.boundaries).read_text(encoding="utf-8"))
        boundary_sheet(a.video, seg["events"], a.out, thumb=a.thumb, pre=a.b_pre, mid=a.b_mid, post=a.b_post)
    else:
        fixed_rate_sheets(a)


if __name__ == "__main__":
    main()
