"""Expected caption words for a reel, on the REEL timeline: the rough cut's own words
(rough-cut/cut_words.json, output timeline o, already checked against the source) mapped
through reel/reel-plan.json. Words whose middle falls inside a clip are kept.

Usage: python3 reel_words.py <edit_dir> <out.json>
Writes {"words": [{text, start, end, o}]}: the input of caption_words.py.
"""
import json, sys
from pathlib import Path
E = Path(sys.argv[1])
fps = 24000 / 1001
plan = json.load(open(E / "reel/reel-plan.json"))
ws = [w for w in json.load(open(E / "rough-cut/cut_words.json"))["words"] if w.get("type") == "word"]
out = []
for c in plan["clips"]:
    a, b = c["o_frame"] / fps, (c["o_frame"] + c["frames"]) / fps
    r0 = c["reel_frame"] / fps
    for w in ws:
        m = (w["start"] + w["end"]) / 2
        if a <= m < b:
            out.append({"text": w["text"].strip(), "start": round(max(a, w["start"]) - a + r0, 3),
                        "end": round(min(b, w["end"]) - a + r0, 3), "o": round(w["start"], 3)})
Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True)
json.dump({"words": out}, open(sys.argv[2], "w"), indent=1)
print(f"{len(out)} words on the reel timeline: {' '.join(w['text'] for w in out)}")
