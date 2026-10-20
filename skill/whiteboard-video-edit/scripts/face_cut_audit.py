"""Audit: for every 0.25 s pose sample on a cut's output timeline, what fraction of the speaker's face box
is inside the viewport. A face that is 10% to 90% inside is a half-cut face at the frame edge."""
import json, sys
E = sys.argv[1]; cam_file = sys.argv[2]; ar = eval(sys.argv[3]); timeline = sys.argv[4]  # 'lf' or 'reel'
FPS = 24000 / 1001
cam = json.load(open(f"{E}/{cam_file}"))["camera"]
rows = sorted((json.loads(l) for l in open(f"{E}/frames/pose_4fps.jsonl")), key=lambda r: r["path"])
faces = [r.get("face") for r in rows]
if timeline == "reel":
    segs = json.load(open(f"{E}/reel/reel-plan.json"))["segments"]
    def o_of(f):
        for s in segs:
            if s["outFrame"] <= f < s["outFrame"] + s["frames"]:
                return (s["o_frame"] + f - s["outFrame"]) / FPS
else:
    o_of = lambda f: f / FPS
half, out_, total, worst = 0, 0, 0, []
for f in range(0, len(cam), 6):
    o = o_of(f); k = int(round(o * 4))
    if k >= len(faces) or not faces[k]: continue
    x, y, w, h = faces[k][0] * 3840, faces[k][1] * 2160, faces[k][2] * 3840, faces[k][3] * 2160
    x0, y0, vw = cam[f]; vh = vw / ar
    ix = max(0, min(x + w, x0 + vw) - max(x, x0)); iy = max(0, min(y + h, y0 + vh) - max(y, y0))
    frac = ix * iy / (w * h)
    total += 1
    if 0.1 < frac < 0.9: half += 1; worst.append((round(f / FPS, 2), round(frac, 2)))
    elif frac <= 0.1: out_ += 1
print(json.dumps({"samples": total, "face_fully_or_mostly_in": total - half - out_, "half_cut_face": half, "face_out_of_frame": out_, "half_cut_times": worst[:40]}))
