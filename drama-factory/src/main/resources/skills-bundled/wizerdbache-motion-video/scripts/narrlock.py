"""Do section changes follow the narration? Event times vs narration line starts.

Inputs: a segments.json (scripts/segments.py) and a transcript .srt of the same video (for example
from any ASR tool). For every event after --skip-before seconds, dt = event - nearest line
start. The statistic is the median |dt|. The control is the same events each shifted by an
independent uniform offset in +-shift s (default 3 s, 2000 repetitions, fixed seed): p = share of
shifted sets whose median |dt| is at least as small as the observed one.

Reported: n events, n lines, median |dt|, share within +-0.5 s, null mean and p05, p.

Calibration (selftest, synthetic lines every 2-4 s): events at line starts + N(0, 0.25 s) must give
p < 0.05 and median |dt| < 0.35 s; events placed uniformly at random must give p > 0.1 in at
least 4 of 5 seeds.

What it cannot determine: whether an event is a section change or a large in-section reveal
(segments.py limit); dense narration (a line every ~2 s) makes every event close to some line
start, which the shifted control absorbs but also makes weaker. Machine transcripts split lines
where the engine chose, so a line start is a pause the engine heard, not the script's line.
Transcript timing error propagates into dt.

Usage:
    python -X utf8 scripts/narrlock.py --segments <segments.json> --srt <file.srt> [--out <file.json>]
    python -X utf8 scripts/narrlock.py --selftest
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

TS = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d\d\d)\s*-->")


def srt_starts(text):
    return sorted(int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000 for h, m, s, ms in TS.findall(text))


def med_abs_dt(events, starts):
    s = np.asarray(starts)
    d = np.abs(np.asarray(events)[:, None] - s[None, :]).min(axis=1)
    return float(np.median(d)), d


def lock(events, starts, shift=3.0, reps=2000, seed=0):
    events = np.asarray(events, float)
    obs, d = med_abs_dt(events, starts)
    rng = np.random.default_rng(seed)
    null = np.array([med_abs_dt(events + rng.uniform(-shift, shift, size=events.size), starts)[0]
                     for _ in range(reps)])
    return {"n_events": int(events.size), "n_lines": len(starts), "median_abs_dt_s": round(obs, 3),
            "within_0_5s": round(float((d <= 0.5).mean()), 3),
            "null_mean_s": round(float(null.mean()), 3), "null_p05_s": round(float(np.percentile(null, 5)), 3),
            "p": round(float((null <= obs).mean()), 4), "shift_s": shift, "reps": reps}


def analyse(segments_path, srt_path, skip_before=2.0, shift=3.0):
    seg = json.loads(Path(segments_path).read_text(encoding="utf-8"))
    starts = srt_starts(Path(srt_path).read_text(encoding="utf-8"))
    ev = [e["t"] for e in seg["events"] if e.get("kind", "transition") == "transition" and e["t"] >= skip_before]
    if len(ev) < 3 or len(starts) < 3:
        return {"segments": str(segments_path), "srt": str(srt_path), "n_events": len(ev), "n_lines": len(starts),
                "verdict": "undetermined: fewer than 3 events or lines"}
    res = lock(ev, starts, shift=shift)
    res.update({"segments": str(segments_path), "srt": str(srt_path), "skip_before_s": skip_before,
                "events": ev,
                "dt": [round(t - min(starts, key=lambda s: abs(t - s)), 3) for t in ev]})
    return res


def selftest():
    ok = True
    rng = np.random.default_rng(7)
    starts = np.cumsum(rng.uniform(2.0, 4.0, size=60))
    ev = np.sort(rng.choice(starts, size=15, replace=False) + rng.normal(0, 0.25, size=15))
    r = lock(ev, starts)
    good = r["p"] < 0.05 and r["median_abs_dt_s"] < 0.35
    print(f"known-true (events at line starts +- 0.25 s): median {r['median_abs_dt_s']} s, p {r['p']} "
          f"(want p < 0.05, median < 0.35) -> {'ok' if good else 'FAIL'}")
    ok &= good
    passed = 0
    for seed in range(5):
        rr = np.random.default_rng(100 + seed)
        ev2 = np.sort(rr.uniform(starts[0], starts[-1], size=15))
        r2 = lock(ev2, starts, seed=seed)
        passed += r2["p"] > 0.1
        print(f"  known-false seed {seed} (uniform random events): median {r2['median_abs_dt_s']} s, p {r2['p']}")
    good = passed >= 4
    print(f"known-false: p > 0.1 in {passed}/5 seeds (want >= 4) -> {'ok' if good else 'FAIL'}")
    ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments")
    ap.add_argument("--srt")
    ap.add_argument("--out")
    ap.add_argument("--skip-before", type=float, default=2.0, help="ignore events before this time (opening fade)")
    ap.add_argument("--shift", type=float, default=3.0)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    res = analyse(a.segments, a.srt, a.skip_before, a.shift)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print({k: v for k, v in res.items() if k not in ("events", "dt")})


if __name__ == "__main__":
    main()
