"""Measure one showreel arm (r9-c21 onward): motion, sections, on-screen numbers vs the site data, data use.

Per video (all through calibrated tools, each with its own --selftest):
  density.py   -> moving share, still runs, fill
  segments.py  -> full-frame change events (section boundaries it can see) and their spacing
  sheets.py    -> whole-film 1 fps sheet for the reader
  fidelity.py  -> (when --html and --corpus are given) on-screen DOM text and numbers vs the corpus
New arithmetic here (covered by --selftest):
  sourced_numbers  -> distinct on-screen numbers fidelity.py would audit that ARE in the number corpus
                      (steady strings + count-up finals, minus the unsourced list)
  data_coords_share -> share of the dataset's coordinates (lat values) that occur verbatim in the
                      build's text files (.html/.js/.json/.css/.mjs); 1.0 when the build ships the data file,
                      ~0 when it never reads it. It says the data reached the build, not that it is on screen.
  data_coords_projected_share -> the same data reaching the build as projected screen points, in dataset order
  first_<mark>_s   -> first sample of >= 2 consecutive samples whose joined on-screen text matches a --mark regex

Usage:
    python -X utf8 scripts/measure_showreel.py <final.mp4> --out <dir> [--html <index.html> --corpus <corpus.json>]
        [--dataset <shops.json> --build <build dir>]
    python -X utf8 scripts/measure_showreel.py --aggregate "A=dir,dir,dir" "B=dir,dir,dir" [--ref "C21=dir"] --out <md>
    python -X utf8 scripts/measure_showreel.py --selftest
"""
import argparse
import json
import re
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from avio import probe  # noqa: E402
from fidelity import numbers_in  # noqa: E402

TEXT_EXT = {".html", ".js", ".mjs", ".json", ".css", ".txt"}


def tool(name, *args):
    r = subprocess.run([sys.executable, "-X", "utf8", str(HERE / name), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"{name} exited {r.returncode}: {r.stderr[-400:]}")
    return r.stdout


def sourced_numbers(fid):
    """Distinct audited numbers on screen that are in the number corpus."""
    shown = set()
    for s in fid.get("strings", []):
        shown.update(numbers_in(s["text"]))
    for k in fid.get("counters", []):
        shown.update(numbers_in(k["text"]))
    bad = {u["number"] for u in fid.get("unsourced_numbers", [])}
    return sorted(shown - bad, key=lambda x: float(x))


FLOAT_RE = re.compile(r"-?\d+\.\d+")


def data_coords_share(dataset, build, decimals=3):
    """Share of the dataset's (lat, lng) pairs found in the build as two ADJACENT decimal numbers (either order),
    both rounded to `decimals`. Adjacent pairs, not single values: a lone 3-decimal latitude could match by chance.
    Rounding: builds store coordinates rounded (r9-c21 A1 kept 4 decimals, A2 3, and JSON drops trailing zeros:
    121.600 -> 121.6), so any decimal token is rounded to `decimals` and compared; a coarser rounding of a value
    that is not exact at that precision (25.04 for 25.041) does not match."""
    d = json.loads(Path(dataset).read_text(encoding="utf-8"))
    rows = d["shops"] if isinstance(d, dict) else d
    pairs = {(round(r["lat"], decimals), round(r["lng"], decimals)) for r in rows if r.get("lat") is not None}
    if not pairs:
        return None
    seen = set()
    for f in Path(build).rglob("*"):
        if f.is_file() and f.suffix.lower() in TEXT_EXT and f.stat().st_size < 50_000_000:
            toks = FLOAT_RE.findall(f.read_text(encoding="utf-8", errors="replace"))
            for a, b in zip(toks, toks[1:]):
                x, y = round(float(a), decimals), round(float(b), decimals)
                seen.add((x, y))
                seen.add((y, x))
    return round(len(pairs & seen) / len(pairs), 3)


def first_marks(fid, marks, min_samples=2):
    """marks: {name: regex}. First time each regex matches what is on screen (None if never).
    With fidelity's `sample_text` (visible text nodes joined in DOM order per sample): the first sample of the first
    run of >= `min_samples` consecutive matching samples, so a word split into one span per character still matches
    (r10-c21 A1 animates 書角 per character; the steady-string version read None). Without it: steady strings."""
    out = {}
    samples = fid.get("sample_text")
    for name, pat in marks.items():
        rx = re.compile(pat)
        if samples:
            hit, run = None, 0
            for i, (t, text) in enumerate(samples):
                run = run + 1 if rx.search(text) else 0
                if run == min_samples:
                    hit = samples[i - min_samples + 1][0]
                    break
            out[name] = hit
        else:
            ts = [x["t"] for x in fid.get("strings", []) if rx.search(x["text"])]
            out[name] = min(ts) if ts else None
    return out


PAIR_RE = re.compile(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")


def _ransac_inliers(src, dst, tol, iters=200, seed=0):
    """Points whose (dst_x, dst_y) lie within tol * range of one line per axis in src; the lines are found by RANSAC
    (two-point lines, most joint inliers, then refitted on them), so half the list being unrelated does not bend them
    (a plain least-squares fit read 0.0 on a half-projected list, measure_showreel selftest)."""
    import numpy as np
    n = len(src)
    span = np.ptp(dst, axis=0)
    if n < 2 or (span == 0).any() or (np.ptp(src, axis=0) == 0).any():
        return 0
    rng = np.random.default_rng(seed)
    best_mask = np.zeros(n, bool)
    for _ in range(iters):
        i, j = rng.choice(n, 2, replace=False)
        if (src[i] == src[j]).any():
            continue
        slope = (dst[i] - dst[j]) / (src[i] - src[j])
        mask = (np.abs(dst - (dst[i] + slope * (src - src[i]))) <= tol * span).all(axis=1)
        if mask.sum() > best_mask.sum():
            best_mask = mask
    if best_mask.sum() < 2:
        return int(best_mask.sum())
    ok = np.ones(n, bool)
    for k in (0, 1):
        A = np.vstack([src[best_mask, k], np.ones(best_mask.sum())]).T
        coef, *_ = np.linalg.lstsq(A, dst[best_mask, k], rcond=None)
        ok &= np.abs(coef[0] * src[:, k] + coef[1] - dst[:, k]) <= tol * span[k]
    return int(ok.sum())


def data_coords_projected(dataset, build, tol=0.01):
    """Share of the dataset's coordinates that reach the build PROJECTED: the first two numbers of each bracketed
    list in a build file ([x, y, ...]), taken in file order, fitted to the dataset's (lng, lat) in dataset order by
    one line per axis (RANSAC, either assignment); a point counts when both residuals are within `tol` of
    that axis' range. r10-c21 A1 shipped 1042 screen-space points (x ~ lng, y ~ -lat, r = 0.9999999) that the
    verbatim check reads as 0. Limits: dataset order must be kept (a shuffled or filtered-and-reordered copy reads
    ~0); objects ({x:..,y:..}) and canvas-only data are not seen."""
    import numpy as np
    d = json.loads(Path(dataset).read_text(encoding="utf-8"))
    rows = d["shops"] if isinstance(d, dict) else d
    ll = np.array([[r["lng"], r["lat"]] for r in rows if r.get("lat") is not None], float)
    if len(ll) < 10:
        return None
    best = 0
    for f in Path(build).rglob("*"):
        if not (f.is_file() and f.suffix.lower() in TEXT_EXT and f.stat().st_size < 50_000_000):
            continue
        found = PAIR_RE.findall(f.read_text(encoding="utf-8", errors="replace"))
        pts = np.array([[float(a), float(b)] for a, b in found]) if found else np.zeros((0, 2))
        if len(pts) < 0.5 * len(ll):
            continue
        for start in range(0, len(pts) - int(0.5 * len(ll)) + 1, max(1, len(pts) // 50)):
            seg = pts[start:start + len(ll)]
            n = len(seg)
            for cols in ((0, 1), (1, 0)):
                best = max(best, _ransac_inliers(ll[:n], seg[:, list(cols)], tol))
    return round(best / len(ll), 3)


def measure(video, out, html=None, corpus=None, dataset=None, build=None, marks=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    info = probe(video)
    tool("density.py", video, "--out", out / "density")
    tool("segments.py", video, "--out", out / "segments")
    tool("sheets.py", video, "--out", out / "sheets", "--fps", "1", "--cols", "6", "--rows", "5", "--thumb", "240")
    d = json.loads((out / "density" / "density.json").read_text(encoding="utf-8"))
    seg = json.loads((out / "segments" / "segments.json").read_text(encoding="utf-8"))
    ts = sorted(e.get("t", e.get("mid")) for e in seg["events"])
    gaps = [b - a for a, b in zip([0.0] + ts, ts + [info["duration"]])]
    res = {
        "video": str(video), "duration_s": round(info["duration"], 2), "has_audio": bool(info.get("has_audio")),
        "fill_median": d["fill"]["median"], "moving_share": d["moving_share"],
        "mean_changed_share": d["mean_changed_share"], "still_p90_s": d["still_runs_s"]["p90"],
        "still_max_s": d["still_runs_s"]["max"], "n_events": len(ts),
        "event_gap_median_s": round(st.median(gaps), 2) if gaps else None,
    }
    if html and corpus:
        vp = f"{info['width']}x{info['height']}"
        tool("fidelity.py", html, "--corpus", corpus, "--out", out / "fidelity", "--dur", round(info["duration"] + 0.5, 2),
             "--viewport", vp)
        fid = json.loads((out / "fidelity" / "fidelity.json").read_text(encoding="utf-8"))
        src = sourced_numbers(fid) if fid.get("status") == "OK" else []
        res.update({"fidelity_status": fid.get("status"), "n_strings": fid.get("n_strings"),
                    "share_strings_found": fid.get("share_found"), "n_unsourced_numbers": fid.get("n_unsourced_numbers"),
                    "n_sourced_numbers": len(src), "sourced_numbers": src, "n_counters": fid.get("n_counters"),
                    "canvas_present": fid.get("canvas_present"), "viewport": vp})
        for k, v in first_marks(fid, marks or {}).items():
            res[f"first_{k}_s"] = v
    if dataset and build:
        res["data_coords_share"] = data_coords_share(dataset, build)
        res["data_coords_projected_share"] = data_coords_projected(dataset, build)
    (out / "measure_showreel.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return res


ROWS = [("長度 s", "duration_s"), ("有在動的時間比例", "moving_share"), ("平均每格變化面積", "mean_changed_share"),
        ("靜止段 p90 s", "still_p90_s"), ("最長靜止 s", "still_max_s"), ("畫面填充 fill 中位數", "fill_median"),
        ("全畫面變化事件數", "n_events"), ("事件間隔中位數 s", "event_gap_median_s"),
        ("畫面文字串數", "n_strings"), ("文字在網站裡找得到的比例", "share_strings_found"),
        ("資料裡找得到的數字（相異）", "n_sourced_numbers"), ("資料裡找不到的數字", "n_unsourced_numbers"),
        ("數字跳動（count-up）數", "n_counters"), ("資料座標進入成品的比例", "data_coords_share"),
        # data_coords_projected_share stays in the json only: alone it reads the STORAGE format (r9: A in-order arrays
        # 1.0, B objects 0.0, both using every coordinate), so the table shows the any-form share instead
        ("資料座標進入成品的比例（任一形式）", "data_coords_any_share"),
        ("品牌字第一次出現 s（任何文字，含資料來源小字；不是品牌標誌）", "first_brand_s"),
        ("資料總數第一次出現 s", "first_total_s")]


def summarize(vals):
    vals = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return {"mean": st.mean(vals), "min": min(vals), "max": max(vals), "n": len(vals)} if vals else None


def overlap(a, b):
    if not a or not b or a["n"] < 3 or b["n"] < 3:
        return "n<3"
    return "重疊" if a["min"] <= b["max"] and b["min"] <= a["max"] else "**不重疊**"


def table(groups, refs=()):
    names = [g for g, _ in groups] + [r for r, _ in refs]
    lines = ["| 量測 | " + " | ".join(f"{g}（mean / min–max, n）" for g, _ in groups)
             + "".join(f" | {r}" for r, _ in refs) + (" | 前兩組範圍" if len(groups) >= 2 else "") + " |",
             "|---|" + "---|" * (len(names) + (1 if len(groups) >= 2 else 0))]
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
    def load(d):
        m = json.loads((Path(d) / "measure_showreel.json").read_text(encoding="utf-8"))
        both = [m.get(k) for k in ("data_coords_share", "data_coords_projected_share") if m.get(k) is not None]
        if both:
            m["data_coords_any_share"] = max(both)
        return m
    g = [(n, [load(d) for d in dirs]) for n, dirs in groups]
    r = [(n, [load(d)]) for n, d in refs]
    lines = ["<!-- GENERATED by scripts/measure_showreel.py --aggregate; do not edit -->"] + table(g, r) + [""]
    for n, ms in g:
        for d, m in zip(dict(groups)[n], ms):
            lines.append(f"- {n} `{d}`: sourced numbers {m.get('sourced_numbers', '—')}")
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("  ok  " if cond else "  FAIL") + " " + name)

    # sourced_numbers: known-true and known-false on a synthetic fidelity result
    fid = {"strings": [{"text": "1,085 間書店"}, {"text": "22 個縣市"}, {"text": "新開 48 間"}, {"text": "第 3 名"}],
           "counters": [{"text": "96 場"}], "unsourced_numbers": [{"number": "48"}]}
    got = sourced_numbers(fid)
    check(f"sourced numbers = 22, 96, 1085 (got {got}); invented 48 excluded, bare 3 not audited", got == ["22", "96", "1085"])
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        rows = [{"lat": 25.04123, "lng": 121.56788}, {"lat": 24.15021, "lng": 120.66349}, {"lat": None, "lng": None}]
        tz_rows = [{"lat": 22.50012, "lng": 120.30004}]  # rounds to 22.500 / 120.300
        (td / "shops.json").write_text(json.dumps({"shops": rows}), encoding="utf-8")
        builds = {
            "yes": ("data.js", "const P=[[25.04123,121.56788],[24.15021,120.66349]]"),
            "rounded4_lnglat": ("data.js", "D=[[121.5679, 25.0412, 'x'], [120.6635, 24.1502, 'y']]"),  # A1 shape
            "rounded2": ("index.html", "<p>25.04 121.57 24.15 120.66 look-alikes</p>"),
            "lat_only": ("a.json", "[25.041, 24.150, 118.321, 23.9]"),  # right lats, wrong partners
            "half": ("a.json", "[[25.041, 121.568]]"),
        }
        (td / "tz.json").write_text(json.dumps({"shops": tz_rows}), encoding="utf-8")
        (td / "tz").mkdir()
        (td / "tz" / "data.js").write_text("D=[[120.3, 22.5, 1]]", encoding="utf-8")  # A2 shape: trailing zeros dropped
        for name, (fn, body) in builds.items():
            (td / name).mkdir()
            (td / name / fn).write_text(body, encoding="utf-8")
        got = {n: data_coords_share(td / "shops.json", td / n) for n in builds}
        check(f"coords share: build with the data = 1.0 ({got['yes']})", got["yes"] == 1.0)
        check(f"coords share: 4-decimal (lng, lat) = 1.0 ({got['rounded4_lnglat']})", got["rounded4_lnglat"] == 1.0)
        check(f"coords share: 2-decimal look-alikes = 0.0 ({got['rounded2']})", got["rounded2"] == 0.0)
        check(f"coords share: latitudes without their longitudes = 0.0 ({got['lat_only']})", got["lat_only"] == 0.0)
        check(f"coords share: one of two = 0.5 ({got['half']})", got["half"] == 0.5)
        tz = data_coords_share(td / "tz.json", td / "tz")
        check(f"coords share: trailing zeros dropped (120.3, 22.5) = 1.0 ({tz})", tz == 1.0)
        import numpy as np
        rng = np.random.default_rng(3)
        ll = np.column_stack([rng.uniform(120.1, 121.9, 200), rng.uniform(21.9, 25.3, 200)])
        (td / "proj.json").write_text(json.dumps({"shops": [{"lng": a, "lat": b} for a, b in ll] + [{"lat": None}]}),
                                      encoding="utf-8")
        merc = np.log(np.tan(np.pi / 4 + np.radians(ll[:, 1]) / 2))
        shapes = {
            "linear": np.column_stack([(ll[:, 0] - 120) * 240 + 12, (25.4 - ll[:, 1]) * 200 + 5]),  # A1 shape
            "mercator": np.column_stack([(ll[:, 0] - 120) * 240, -merc * 11000]),
            "shuffled": np.column_stack([(ll[:, 0] - 120) * 240, (25.4 - ll[:, 1]) * 200])[rng.permutation(200)],
            "random": rng.uniform(0, 700, (200, 2)),
            "half": np.vstack([np.column_stack([(ll[:100, 0] - 120) * 240, (25.4 - ll[:100, 1]) * 200]),
                               rng.uniform(0, 700, (100, 2))]),
        }
        pgot = {}
        for name, pts in shapes.items():
            (td / ("p_" + name)).mkdir()
            (td / ("p_" + name) / "data.js").write_text(
                "window.D={pts:[" + ",".join(f"[{x:.1f},{y:.1f},2010,0]" for x, y in pts) + "]}", encoding="utf-8")
            pgot[name] = data_coords_projected(td / "proj.json", td / ("p_" + name))
        check(f"projected coords: linear screen points in order = 1.0 ({pgot['linear']})", pgot["linear"] == 1.0)
        check(f"projected coords: Mercator y, 1 decimal = 1.0 ({pgot['mercator']})", pgot["mercator"] == 1.0)
        check(f"projected coords: same points shuffled < 0.1 ({pgot['shuffled']})", pgot["shuffled"] < 0.1)
        check(f"projected coords: random points < 0.1 ({pgot['random']})", pgot["random"] < 0.1)
        check(f"projected coords: half in order, half random ~0.5 ({pgot['half']})", 0.45 <= pgot["half"] <= 0.6)
    fm = first_marks({"strings": [{"t": 4.25, "text": "書角 Bookcorner"}, {"t": 0.5, "text": "1,085"},
                                  {"t": 9.0, "text": "書角"}]}, {"brand": "書角|Bookcorner", "total": r"1,?085", "none": "zzz"})
    check(f"first marks: brand 4.25, total 0.5, never -> None ({fm})", fm == {"brand": 4.25, "total": 0.5, "none": None})
    samp = {"sample_text": [[0.0, "角"], [0.25, "書角讀書會"], [0.5, "書角"], [0.75, "x"], [1.0, "書"], [1.25, "角"],
                            [1.5, "1,085間"], [1.75, "1085 間"]]}
    fm2 = first_marks(samp, {"brand": "書角", "total": r"1,?085", "none": "zzz"})
    check(f"first marks from joined sample text: per-character brand from 0.25 (a lone 角 at 0.0 and 書 / 角 on "
          f"separate samples do not count), total 1.5, never None ({fm2})", fm2 == {"brand": 0.25, "total": 1.5, "none": None})
    fm3 = first_marks({"sample_text": [[0.0, "書角"], [0.25, "x"], [0.5, "書角"]]}, {"brand": "書角"})
    check(f"first marks: one-sample flashes never count ({fm3})", fm3 == {"brand": None})
    a = [{"moving_share": v} for v in (0.5, 0.55, 0.6)]
    b = [{"moving_share": v} for v in (0.8, 0.85, 0.9)]
    c = [{"moving_share": v} for v in (0.58, 0.7, 0.75)]
    check("overlap: separated ranges -> 不重疊", "**不重疊**" in table([("A", a), ("B", b)])[3])
    check("overlap: touching ranges -> 重疊", "| 重疊 |" in table([("A", a), ("C", c)])[3])
    check("overlap: n<3 is never a verdict", "n<3" in table([("A", a[:2]), ("B", b)])[3])
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--html")
    ap.add_argument("--corpus")
    ap.add_argument("--dataset")
    ap.add_argument("--build")
    ap.add_argument("--mark", action="append", default=[], help="NAME=regex: first time a steady string matches")
    ap.add_argument("--aggregate", nargs="+", help='"NAME=dir,dir" ...')
    ap.add_argument("--ref", nargs="*", default=[], help='"NAME=dir" single-video reference columns')
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.aggregate:
        groups = [(s.split("=", 1)[0], s.split("=", 1)[1].split(",")) for s in a.aggregate]
        refs = [tuple(s.split("=", 1)) for s in a.ref]
        aggregate(groups, refs, a.out)
        return
    marks = dict(m.split("=", 1) for m in a.mark)
    print(json.dumps(measure(a.video, a.out, a.html, a.corpus, a.dataset, a.build, marks), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
