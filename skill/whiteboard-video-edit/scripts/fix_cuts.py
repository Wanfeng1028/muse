"""Post-pass on a finished zoom plan: every cut must change framing (score >= 1, see
plan_zooms.differ). A shot that fails gets its cut framing loosened 1.2x about the same centre
(or tightened when loosening would pass the full frame), and its per-frame camera is rebuilt
from the new base with its planned eased moves unchanged. Prints the frame range it changed."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from plan_zooms import ease, rect_of, clamp, differ, SW  # noqa: E402

E = Path(sys.argv[1])
plan = json.load(open(E / "zoom-plan.json"))
if len(sys.argv) < 3:
    raise SystemExit("usage: python3 fix_cuts.py <edit_dir> <label>   (camera_<label>.json, zoom-plan.json)")
LBL = sys.argv[2]
cam = json.load(open(E / f"camera_{LBL}.json"))["camera"]
F = lambda c: [c[0] + c[2] / 2, c[1] + c[2] * 9 / 32, c[2]]
changed = []
for k, s in enumerate(plan["shots"]):
    if k == 0:
        continue
    f0 = s["out_frame"]
    prev = F(cam[f0 - 1])
    base = [s["framing"]["cx"], s["framing"]["cy"], s["framing"]["w"]]
    if differ(base, prev) >= 1:
        continue
    # prefer looser framings (the speaker's face and hands stay in), the full wide last-but-one, tighter only as a last resort
    for w2 in (base[2] * 1.2, base[2] * 1.4, SW, base[2] / 1.2, base[2] / 1.4):
        G = clamp(base[0], base[1], w2)
        if differ(G, prev) >= 1:
            break
    s["framing"].update({"cx": G[0], "cy": G[1], "w": G[2], "scale": round(SW / G[2], 3),
                         "name": s["framing"]["name"].split(" ")[0] + f" {SW / G[2]:.2f}x", "fit": s["framing"]["fit"] + "; cut change enforced"})
    A = G
    mv = list(s["moves"])
    for f in range(f0, f0 + s["frames"]):
        while mv and f >= mv[0]["start_frame"] + mv[0]["frames"]:
            m = mv.pop(0); A = [m["to"]["cx"], m["to"]["cy"], m["to"]["w"]]
        if mv and f >= mv[0]["start_frame"]:
            m = mv[0]; p = ease((f - m["start_frame"]) / m["frames"])
            B = [m["to"]["cx"], m["to"]["cy"], m["to"]["w"]]
            ra, rb = rect_of(A), rect_of(B)
            cam[f] = [round(ra[0] + (rb[0] - ra[0]) * p, 4), round(ra[1] + (rb[1] - ra[1]) * p, 4), round(A[2] + (B[2] - A[2]) * p, 4)]
        else:
            ra = rect_of(A); cam[f] = [round(ra[0], 4), round(ra[1], 4), round(A[2], 4)]
    changed.append((s["seg"], f0, f0 + s["frames"] - 1, round(differ(G, prev), 2)))
json.dump(plan, open(E / "zoom-plan.json", "w"), indent=1)
json.dump({"camera": cam}, open(E / f"camera_{LBL}.json", "w"))
print(json.dumps(changed))
