"""Word-level timecodes -> words.json (the anchor source for storyboards).

  python3 -m timeline.words --whisper source_local_asr.json --compiled compiled.json \
          --media voice-candidate.mp4 --out words.json

--whisper   whisper / mlx-whisper JSON with segments[].words[] = {word, start, end, probability}
--compiled  optional jianying-compiled-plan/v1 (ranges: source_start_us, source_duration_us,
            target_start_us). Word times are mapped from the raw take to the edited cut;
            words that were cut out are dropped.
--media     the video these word times belong to. Storyboard base clips with the same
            src pick the words up automatically (timeline = at + (t - in)).

words.json = {version, clock:"media", media, provenance, words:[{i, w, s, e, p}]}
"""
import argparse
import json
from pathlib import Path


def load_whisper(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for seg in d.get("segments", []):
        for w in seg.get("words", []):
            txt = (w.get("word") or "").strip()
            if not txt:
                continue
            out.append({"w": txt, "s": float(w["start"]), "e": float(w["end"]), "p": round(float(w.get("probability", 1.0)), 3)})
    return out


def map_ranges(words, compiled):
    rs = [(r["source_start_us"] / 1e6, (r["source_start_us"] + r["source_duration_us"]) / 1e6, r["target_start_us"] / 1e6)
          for r in compiled["ranges"]]
    out = []
    for w in words:
        best = None
        for ss, se, ts in rs:
            ov = min(w["e"], se) - max(w["s"], ss)
            if ov <= 0:
                continue
            if best is None or ov > best[0]:
                best = (ov, ss, se, ts)
        if not best:
            continue
        ov, ss, se, ts = best
        if ov < 0.5 * max(1e-3, w["e"] - w["s"]):
            continue
        s, e = max(w["s"], ss), min(w["e"], se)
        out.append({**w, "s": round(ts + s - ss, 4), "e": round(ts + e - ss, 4), "src_s": w["s"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--whisper", required=True)
    ap.add_argument("--compiled")
    ap.add_argument("--media", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    words = load_whisper(a.whisper)
    prov = {"whisper": str(Path(a.whisper).resolve()), "n_source_words": len(words)}
    if a.compiled:
        comp = json.loads(Path(a.compiled).read_text(encoding="utf-8"))
        words = map_ranges(words, comp)
        prov["compiled"] = str(Path(a.compiled).resolve())
        prov["mapping"] = "source -> target via compiled.ranges (words mostly outside kept ranges dropped)"
    for i, w in enumerate(words):
        w["i"] = i
    doc = {"version": "0.1", "clock": "media", "media": str(Path(a.media).resolve()), "provenance": prov,
           "words": [{"i": w["i"], "w": w["w"], "s": w["s"], "e": w["e"], "p": w["p"]} for w in words]}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"wrote {a.out}: {len(words)} words ({prov['n_source_words']} in source)")


if __name__ == "__main__":
    main()
