"""Face and head joints for EVERY frame of a reel (not the 4 per second track), so overlay
keep out boxes follow the speaker's head exactly, even when the speaker moves fast.

Usage: python3 reel_faces.py <props.json> <out_dir>
Decodes each reel segment's source frames (frame exact seek, as the renderer does) at
960x540, runs tools/pose (Apple Vision) on them, and writes <out_dir>/faces_perframe.json:
a list, one entry per reel frame, of [x0, y0, x1, y1] in 4K source pixels or null.
"""
import json, subprocess, sys
from pathlib import Path

props = json.load(open(sys.argv[1]))
out = Path(sys.argv[2])
fr = out / "faceframes"
fr.mkdir(parents=True, exist_ok=True)
POSE = Path(__file__).parent / "pose"
SW, SH = props["srcW"], props["srcH"]
n_total = sum(s["frames"] for s in props["segments"])
for s in props["segments"]:
    t = (s["srcFrame"] - 0.25) * 1001 / 24000
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-hwaccel", "videotoolbox", "-ss", f"{t:.6f}", "-i", props["src"],
                    "-map", "0:v:0", "-frames:v", str(s["frames"]), "-vf", "scale=960:540", "-q:v", "3",
                    "-start_number", str(s["outFrame"]), str(fr / "r_%05d.jpg")], check=True)
files = sorted(fr.glob("r_*.jpg"))
assert len(files) == n_total, (len(files), n_total)
res = {}
B = 120
for i in range(0, len(files), B):
    chunk = files[i:i + B]
    p = subprocess.run([str(POSE)] + [str(f) for f in chunk], capture_output=True, text=True, check=True)
    for line in p.stdout.splitlines():
        r = json.loads(line)
        res[int(r["path"][2:7])] = r
faces, miss = [], 0
for f in range(n_total):
    r = res.get(f, {})
    fc = r.get("face")
    j = r.get("joints", {})
    head = [j[n] for n in ("nose", "lEye", "rEye", "lEar", "rEar") if n in j and j[n][2] >= 0.3]
    box = None
    if fc:
        box = [fc[0] * SW, fc[1] * SH, (fc[0] + fc[2]) * SW, (fc[1] + fc[3]) * SH]
        # a face box that holds none of the speaker's head joints is a drawing on the board, not the speaker
        if head and not any(box[0] <= p[0] * SW <= box[2] and box[1] <= p[1] * SH <= box[3] for p in head):
            box = None
    if box is None and head:
        # head seen from the side or behind: a box around the head joints, typical face size
        xs = [p[0] * SW for p in head]; ys = [p[1] * SH for p in head]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        box = [cx - 110, cy - 120, cx + 110, cy + 150]
    if box is None:
        miss += 1
    faces.append([round(v, 1) for v in box] if box else None)
json.dump({"note": "per reel frame face box in 4K source px (Vision face, validated by head joints)", "faces": faces},
          open(out / "faces_perframe.json", "w"))
print(f"{n_total} frames, {n_total - miss} with a face or head, {miss} without")
