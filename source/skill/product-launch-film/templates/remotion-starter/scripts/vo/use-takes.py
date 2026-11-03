#!/usr/bin/env python3
"""Assemble the picked narration takes into the film.

  python3 scripts/vo/use-takes.py --pick 01-s1=vo-takes/take2 [--pick 02-x=vo-takes/take1 ...] [--start 01-s1=30]

For each line: copies <take>/<id>.wav (from process-vo.sh; falls back to .mp3) to public/audio/vo/<id>.<ext>,
and writes src/vo-manifest.json with {id, start, file, seconds, speechEnd} using the take's manifest.json
measurements. `start` defaults to the line's start in src/vo-script.json. Then retime src/timeline.ts so every
line ends inside its scene (speechEnd + ~0.3 s of air before the cut).
"""
import argparse, json, os, shutil

ap = argparse.ArgumentParser()
ap.add_argument("--pick", action="append", required=True, help="id=take_dir")
ap.add_argument("--start", action="append", default=[], help="id=absolute_frame")
ap.add_argument("--script", default="src/vo-script.json")
a = ap.parse_args()
script = {l["id"]: l for l in json.load(open(a.script))["lines"]}
starts = dict(s.split("=") for s in a.start)
lines = []
for p in a.pick:
    lid, take = p.split("=")
    m = {l["id"]: l for l in json.load(open(os.path.join(take, "manifest.json")))["lines"]}[lid]
    src = next(os.path.join(take, f"{lid}.{e}") for e in ("wav", "mp3") if os.path.exists(os.path.join(take, f"{lid}.{e}")))
    ext = os.path.splitext(src)[1]
    os.makedirs("public/audio/vo", exist_ok=True)
    shutil.copyfile(src, f"public/audio/vo/{lid}{ext}")
    lines.append({"id": lid, "start": int(starts.get(lid, script[lid]["start"])), "file": f"audio/vo/{lid}{ext}",
                  "seconds": m["seconds"], "speechEnd": m["offset"], "take": os.path.basename(os.path.normpath(take))})
lines.sort(key=lambda l: l["start"])
json.dump({"note": "Written by scripts/vo/use-takes.py", "lines": lines}, open("src/vo-manifest.json", "w"), indent=1)
for l in lines:
    print(f"{l['id']:12s} start {l['start']:5d}  speech ends at frame {l['start'] + round(l['speechEnd'] * 60)}  ({l['take']})")
