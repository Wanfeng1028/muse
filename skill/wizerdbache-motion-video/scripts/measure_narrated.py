"""Measure one narrated explainer video (T06 rounds, r8-c20 on) and aggregate repeated runs.

Per video it runs the calibrated instruments and writes <out>/measure_narrated.json:
    density.py  -> <out>/density/   fill, extent, moving share, still runs
    segments.py -> <out>/segments/  global-change events (section changes)
    ASR CLI (MV_ASR_EXE) -> <out>/asr/transcript.srt  machine transcript, zh; or pass --srt
    narrlock.py -> <out>/narrlock.json  section changes vs narration line starts
    sheets.py   -> <out>/sheets/    whole-film sheet, 1 frame per second (git-ignored)
Nothing here computes a new number from pixels; it collects the instruments' outputs. A video
without an audio stream, or whose transcript has fewer than 3 lines, gets narration "n/a".

--aggregate writes a GENERATED markdown table: mean / min-max / n per condition, plus a column
saying whether the first two conditions' ranges overlap (the I-6 reading: an effect needs >= 3 runs
per condition and non-overlapping ranges).

Usage:
    python -X utf8 scripts/measure_narrated.py <final.mp4> --out <dir> [--srt <existing.srt>]
    python -X utf8 scripts/measure_narrated.py --aggregate "A=d1,d2,d3" "B=d4,d5,d6" [--ref "C20=dir"] --out table.md
    python -X utf8 scripts/measure_narrated.py --selftest
"""
import argparse
import json
import os
import shutil
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from avio import probe  # noqa: E402


def tool(name, *args):
    r = subprocess.run([sys.executable, "-X", "utf8", str(HERE / name), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"{name} exited {r.returncode}: {r.stderr[-400:]}")
    return r.stdout


def transcribe(video, out_dir):
    # MV_ASR_EXE: any ASR command taking `<video> --out <dir> --language zh --stem transcript`
    # and writing <dir>/transcript.srt. Without it, transcribe elsewhere and pass --srt.
    exe = os.environ.get("MV_ASR_EXE")
    if not exe:
        return None, "no ASR command (set MV_ASR_EXE or pass --srt)"
    out_dir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([exe, str(video), "--out", str(out_dir), "--language", "zh", "--stem", "transcript"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    srt = out_dir / "transcript.srt"
    if r.returncode or not srt.exists():
        return None, f"ASR command exited {r.returncode}: {r.stderr[-300:]}"
    return srt, None


def measure(video, out, srt=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    info = probe(video)
    tool("density.py", video, "--out", out / "density")
    tool("segments.py", video, "--out", out / "segments")
    tool("sheets.py", video, "--out", out / "sheets", "--fps", "1", "--cols", "6", "--rows", "5", "--thumb", "240")
    note = None
    if srt is None and info.get("has_audio"):
        srt, note = transcribe(video, out / "asr")
    elif not info.get("has_audio"):
        note = "no audio stream"
    nl = None
    if srt:
        tool("narrlock.py", "--segments", out / "segments" / "segments.json", "--srt", srt,
             "--out", out / "narrlock.json")
        nl = json.loads((out / "narrlock.json").read_text(encoding="utf-8"))
    d = json.loads((out / "density" / "density.json").read_text(encoding="utf-8"))
    seg = json.loads((out / "segments" / "segments.json").read_text(encoding="utf-8"))
    res = {
        "video": str(video), "duration_s": round(info["duration"], 2), "has_audio": bool(info.get("has_audio")),
        "fill_median": d["fill"]["median"], "extent_median": d["extent"]["median"],
        "moving_share": d["moving_share"], "mean_changed_share": d["mean_changed_share"],
        "still_median_s": d["still_runs_s"]["median"], "still_p90_s": d["still_runs_s"]["p90"],
        "still_max_s": d["still_runs_s"]["max"],
        "n_events": len(seg["events"]),
        "narration": "n/a" if not nl or "p" not in nl else "measured",
        "narration_note": note or (nl.get("verdict") if nl and "p" not in nl else None),
        "n_lines": nl.get("n_lines") if nl else None,
        "narr_median_abs_dt_s": nl.get("median_abs_dt_s") if nl else None,
        "narr_null_mean_s": nl.get("null_mean_s") if nl else None,
        "narr_p": nl.get("p") if nl else None,
        "srt": str(srt) if srt else None,
    }
    (out / "measure_narrated.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return res


ROWS = [
    ("長度 s", "duration_s"), ("畫面填充 fill 中位數", "fill_median"), ("內容範圍 extent 中位數", "extent_median"),
    ("有在動的時間比例", "moving_share"), ("靜止段中位數 s", "still_median_s"), ("靜止段 p90 s", "still_p90_s"),
    ("最長靜止 s", "still_max_s"), ("全畫面變化事件數", "n_events"), ("旁白句數（轉寫）", "n_lines"),
    ("換段離旁白句首 中位差 s", "narr_median_abs_dt_s"), ("對照組中位差 s", "narr_null_mean_s"),
    ("換段跟旁白 p", "narr_p"),
]


def summarize(vals):
    vals = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not vals:
        return None
    return {"mean": st.mean(vals), "min": min(vals), "max": max(vals), "n": len(vals)}


def overlap(a, b):
    if not a or not b or a["n"] < 3 or b["n"] < 3:
        return "n<3"
    return "重疊" if a["min"] <= b["max"] and b["min"] <= a["max"] else "**不重疊**"


def table(groups, refs=()):
    """groups/refs: [(name, [measure dicts])]. Returns markdown lines."""
    names = [g for g, _ in groups] + [r for r, _ in refs]
    head = ["| 量測 | " + " | ".join(f"{g}（mean / min–max, n）" for g, _ in groups)
            + "".join(f" | {r}" for r, _ in refs) + (" | 前兩組範圍" if len(groups) >= 2 else "") + " |",
            "|---|" + "---|" * (len(names) + (1 if len(groups) >= 2 else 0))]
    lines = list(head)
    for label, key in ROWS:
        sums = [summarize([m.get(key) for m in ms]) for _, ms in groups]
        cells = [f"{s['mean']:.3g} / {s['min']:.3g}–{s['max']:.3g}, {s['n']}" if s else "—" for s in sums]
        for _, ms in refs:
            v = ms[0].get(key)
            cells.append(f"{v:.3g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else "—")
        if len(groups) >= 2:
            cells.append(overlap(sums[0], sums[1]))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return lines


def aggregate(groups, refs, out):
    load = lambda d: json.loads((Path(d) / "measure_narrated.json").read_text(encoding="utf-8"))  # noqa: E731
    g = [(n, [load(d) for d in dirs]) for n, dirs in groups]
    r = [(n, [load(d)]) for n, d in refs]
    lines = ["<!-- GENERATED by scripts/measure_narrated.py --aggregate; do not edit -->"] + table(g, r) + [""]
    for n, dirs in groups:
        for d, m in zip(dirs, dict(g)[n]):
            lines.append(f"- {n} `{d}`: narration {m['narration']}"
                         + (f" ({m['narration_note']})" if m.get("narration_note") else ""))
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def selftest():
    """The aggregation is the only new arithmetic here: known inputs -> known cells and overlap verdicts."""
    ok = True
    mk = lambda v: {"moving_share": v}  # noqa: E731
    a = [mk(0.1), mk(0.2), mk(0.3)]
    b = [mk(0.7), mk(0.8), mk(0.9)]
    c = [mk(0.25), mk(0.5), mk(0.6)]
    row = lambda lines: next(l for l in lines if l.startswith("| 有在動的時間比例"))  # noqa: E731,E741
    r1 = row(table([("A", a), ("B", b)]))
    good = "0.2 / 0.1–0.3, 3" in r1 and "0.8 / 0.7–0.9, 3" in r1 and "**不重疊**" in r1
    print(f"known-true separated ranges: {r1} -> {'ok' if good else 'FAIL'}")
    ok &= good
    r2 = row(table([("A", a), ("C", c)]))
    good = r2.rstrip(" |").endswith("重疊") and "不重疊" not in r2
    print(f"known-false overlapping ranges: {r2} -> {'ok' if good else 'FAIL'}")
    ok &= good
    r3 = row(table([("A", a[:2]), ("B", b)]))
    good = "n<3" in r3
    print(f"n<3 is not read as an effect: {r3} -> {'ok' if good else 'FAIL'}")
    ok &= good
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m"
        p.mkdir()
        (p / "measure_narrated.json").write_text(json.dumps({"moving_share": 0.5, "narration": "n/a"}),
                                                 encoding="utf-8")
        aggregate([("A", [str(p)] * 3), ("B", [str(p)] * 3)], [], Path(td) / "t.md")
        good = "重疊" in (Path(td) / "t.md").read_text(encoding="utf-8")
        print(f"file round trip -> {'ok' if good else 'FAIL'}")
        ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--srt", help="use this transcript instead of transcribing")
    ap.add_argument("--aggregate", nargs="+", help='"NAME=dir,dir" ...')
    ap.add_argument("--ref", nargs="*", default=[], help='"NAME=dir" single-video reference columns')
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.aggregate:
        groups = [(g.split("=", 1)[0], g.split("=", 1)[1].split(",")) for g in a.aggregate]
        refs = [(r.split("=", 1)[0], r.split("=", 1)[1]) for r in a.ref]
        aggregate(groups, refs, a.out)
        return
    res = measure(a.video, a.out, Path(a.srt) if a.srt else None)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
