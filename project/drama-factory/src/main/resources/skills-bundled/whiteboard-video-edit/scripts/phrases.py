import json, sys
R = sys.argv[1]
ws = [w for w in json.load(open(f"{R}/cut_words.json"))["words"] if w["type"] in ("word", "audio_event")]
cuts = [c["t"] for c in json.load(open(f"{R}/cuts.json"))]
ci = 0; line = []; t0 = None; prev_end = 0
out = []
for w in ws:
    while ci < len(cuts) and cuts[ci] <= w["start"] + 1e-6:
        if line: out.append(f"[{t0:6.2f}] {' '.join(line)}"); line = []
        out.append(f"   --- cut {ci+1} @ {cuts[ci]:.2f}"); ci += 1
    if line and w["start"] - prev_end > 0.35:
        out.append(f"[{t0:6.2f}] {' '.join(line)}"); line = []
    if not line: t0 = w["start"]
    line.append(w["text"].strip()); prev_end = w["end"]
if line: out.append(f"[{t0:6.2f}] {' '.join(line)}")
open(f"{R}/../output_transcript.txt", "w").write("\n".join(out) + "\n")
