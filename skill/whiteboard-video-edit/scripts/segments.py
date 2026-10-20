"""Rebuild the rendered segment list (source start, whole frames, output offset) from the
rough cut's edl.json + cuts.json, and write segments.json. Checks the frame total."""
import json, sys
from fractions import Fraction
R = sys.argv[1]
edl = json.load(open(f"{R}/edl.json")); cuts = json.load(open(f"{R}/cuts.json")); rep = json.load(open(f"{R}/render_report.json"))
fps = Fraction(24000, 1001)
starts = [edl["ranges"][0]["start"]] + [c["to"]["src_start"] for c in cuts]
offs = [0.0] + [c["t"] for c in cuts]
total = rep["streams"]["video"]["nb_frames"]
segs, acc = [], 0
for i, (s, o) in enumerate(zip(starts, offs)):
    nxt = offs[i + 1] if i + 1 < len(offs) else float(Fraction(total) / fps)
    n = round((nxt - o) * fps)
    # exact output frame offset from the running frame count
    segs.append({"i": i, "src_start": s, "src_frame": round(s * fps), "frames": n, "out_frame": acc, "out_t": float(Fraction(acc) / fps)})
    acc += n
assert acc == total, (acc, total)
for sg, o in zip(segs, offs):
    assert abs(sg["out_t"] - o) < 0.003, (sg, o)
json.dump({"fps": "24000/1001", "total_frames": total, "segments": segs}, open(f"{R}/../segments.json", "w"), indent=1)
print(len(segs), "segments,", total, "frames")
