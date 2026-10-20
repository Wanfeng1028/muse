"""props for subpixel_render(_ov).mjs from segments.json + camera_<label>.json.
Usage: python3 make_props.py <edit_dir> <label> <source_video> [outW outH]"""
import json, sys
from pathlib import Path
E, L, src = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
OW, OH = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (1920, 1080)
segs = json.load(open(E / "segments.json"))["segments"]
cam = json.load(open(E / f"camera_{L}.json"))["camera"]
assert sum(s["frames"] for s in segs) == len(cam)
json.dump({"src": str(Path(src).resolve()), "srcW": 3840, "srcH": 2160, "outW": OW, "outH": OH,
           "segments": [{"srcFrame": s["src_frame"], "frames": s["frames"], "outFrame": s["out_frame"]} for s in segs],
           "camera": cam}, open(E / f"props_{L}_abs.json", "w"))
print(f"props_{L}_abs.json: {len(segs)} segments, {len(cam)} frames, {OW}x{OH}")
