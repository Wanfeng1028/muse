"""Contact sheets of what the viewer sees: crop each 960x540 tracking frame by the planned
viewport (camera file) at the start of every shot and after every move."""
import json, sys
from PIL import Image, ImageDraw
E = sys.argv[1]; cam_file = sys.argv[2]; plan_file = sys.argv[3]; out = sys.argv[4]; aspect = sys.argv[5] if len(sys.argv) > 5 else "16:9"
FPS = 24000 / 1001
cam = json.load(open(f"{E}/{cam_file}"))["camera"]; plan = json.load(open(f"{E}/{plan_file}"))
pts = []
for s in plan["shots"]:
    pts.append((s["out_frame"] + min(6, s["frames"] - 1), f"{s['seg']} {s['framing']['name'][:18]}"))
    for m in s["moves"]:
        pts.append((min(m["start_frame"] + m["frames"] + 3, s["out_frame"] + s["frames"] - 1), f"  > {m['to']['name'][:18]}"))
tw, th = (256, 144) if aspect == "16:9" else (108, 192)
cols = 10 if aspect == "16:9" else 16
rows = (len(pts) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw, rows * (th + 14)), (20, 20, 20))
d = ImageDraw.Draw(sheet)
for i, (f, lab) in enumerate(pts):
    t = f / FPS
    k = int(round(t * 4)) + 1
    src = plan.get("track_frames", "frames/track4")
    im = Image.open(f"{E}/{src}/f_{k:05d}.jpg")
    x0, y0, w = cam[f][:3]
    h = w * 9 / 16 if aspect == "16:9" else w * 16 / 9
    sc = im.width / 3840
    crop = im.crop((x0 * sc, y0 * sc, (x0 + w) * sc, (y0 + h) * sc)).resize((tw, th))
    X, Y = (i % cols) * tw, (i // cols) * (th + 14)
    sheet.paste(crop, (X, Y))
    d.text((X + 2, Y + th + 1), f"{t:.1f}s {lab}", fill=(255, 255, 0))
sheet.save(out, quality=88)
print(len(pts), "thumbnails ->", out)
