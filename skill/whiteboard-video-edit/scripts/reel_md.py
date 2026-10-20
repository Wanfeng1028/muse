"""reel/reel-plan.md from reel/reel-plan.json: the reel's lines (reel time, rough cut time o,
label from clips.json) and its vertical shots (framing at each cut, eased moves inside).
Usage (from the edit dir): python3 reel_md.py [title]"""
import json, sys
p = json.load(open("reel/reel-plan.json"))
title = sys.argv[1] if len(sys.argv) > 1 else p.get("label", "Reel")
L = [f"# {title}", "", f"Length {p['duration_s']:.2f} s, {len(p['clips'])} lines cut from the rough cut at pauses (o = time in the rough cut), "
     f"{p['total_frames']} frames at 24000/1001 fps. Audio is the mastered long form audio cut at the same frame exact edges.", "",
     "## Lines", "", "| Reel time | o | Line |", "| --- | --- | --- |"]
for c in p["clips"]:
    L.append(f"| {c['reel_t']:.2f} s | {c['o_start']:.2f} to {c['o_end']:.2f} | {c['label']} |")
for kind in ("vertical", "horizontal"):
    if kind not in p:
        continue
    L += ["", f"## {kind.capitalize()} shots (a framing change at every cut, eased moves only inside a shot)", "",
          "| Reel time | Frames | Framing at the cut | Eased moves |", "| --- | --- | --- | --- |"]
    for s in p[kind]["shots"]:
        mv = "; ".join(f"{m['t']:.2f} s to {m['to']['name']} ({m['dur_s']:.2f} s)" for m in s["moves"]) or "none"
        L.append(f"| {s['t']:.2f} s | {s['frames']} | {s['framing']['name']} | {mv} |")
open("reel/reel-plan.md", "w").write("\n".join(L) + "\n")
print(f"reel/reel-plan.md: {len(p['clips'])} lines")
