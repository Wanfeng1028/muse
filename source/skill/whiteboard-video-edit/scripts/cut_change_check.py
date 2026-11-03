"""Every cut must change framing: for each shot start in zoom-plan.json, compare the camera on
the last frame before the cut with the first frame after it (plan_zooms.differ: a scale change
of 1.15x or a centre shift of 12% of the window scores 1.0). Read only.
Usage: python3 cut_change_check.py <edit_dir> <label>   (camera_<label>.json, 16:9)"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from plan_zooms import differ  # noqa: E402
E, L = Path(sys.argv[1]), sys.argv[2]
plan = json.load(open(E / "zoom-plan.json"))
cam = json.load(open(E / f"camera_{L}.json"))["camera"]
F = lambda c: [c[0] + c[2] / 2, c[1] + c[2] * 9 / 32, c[2]]
scores = [(s["out_frame"], differ(F(cam[s["out_frame"] - 1]), F(cam[s["out_frame"]]))) for s in plan["shots"][1:]]
bad = [(f, round(d, 2)) for f, d in scores if d < 1]
print(json.dumps({"cuts": len(scores), "pass": len(scores) - len(bad), "min_score": round(min(d for _, d in scores), 2), "fail": bad}))
