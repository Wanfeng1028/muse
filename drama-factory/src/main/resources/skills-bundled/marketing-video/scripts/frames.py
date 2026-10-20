#!/usr/bin/env python3
"""Turn a piece of real footage into numbered frames the scene can show.

The scene swaps an <img> to footage/<name>/NNNN.jpg from seek(t), so footage
stays a pure function of time like everything else. Crop to the aspect the
frame shows on screen, centred on the face.

  frames.py --src clip.mp4 --name anna --start 2.0 --dur 6.5 --aspect 9:16 --cx 0.39
  frames.py --src clip.mp4 --name anna --sheet        # contact sheet to pick a window and cx

--cx is the face centre as a fraction of the source width. Pick the window on
the sheet: avoid a hand over the face, a look away, a cut. Write the window and
cx into brief.md so the next version uses the same footage.
"""
import argparse, pathlib, shutil, subprocess, json

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True); ap.add_argument("--name", required=True)
ap.add_argument("--start", type=float, default=0.0); ap.add_argument("--dur", type=float, default=6.0)
ap.add_argument("--aspect", default="9:16"); ap.add_argument("--cx", type=float, default=0.5)
ap.add_argument("--height", type=int, default=768); ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--sheet", action="store_true")
a = ap.parse_args()

probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
    "stream=width,height:format=duration", "-of", "json", a.src], capture_output=True, text=True, check=True).stdout)
sw, sh = probe["streams"][0]["width"], probe["streams"][0]["height"]
length = float(probe["format"]["duration"])
out = pathlib.Path("footage") / a.name

if a.sheet:
    out.mkdir(parents=True, exist_ok=True)
    step = max(1.0, length / 14)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.src, "-vf",
        f"fps=1/{step:.3f},scale=240:-2,drawtext=text='%{{pts\\:hms}}':x=6:y=6:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.5,tile=7x2:padding=4",
        "-frames:v", "1", str(out / "sheet.jpg")], capture_output=True)
    if not (out / "sheet.jpg").exists():      # ffmpeg built without drawtext
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.src, "-vf",
            f"fps=1/{step:.3f},scale=240:-2,tile=7x2:padding=4", "-frames:v", "1", str(out / "sheet.jpg")], check=True)
    print(f"{out/'sheet.jpg'}  ({length:.1f}s source, one thumbnail every {step:.1f}s, {sw}x{sh})")
    raise SystemExit

aw, ah = (int(v) for v in a.aspect.split(":"))
cw = min(sw, round(sh * aw / ah)); ch = min(sh, round(cw * ah / aw))
x = int(min(max(a.cx * sw - cw / 2, 0), sw - cw)); y = (sh - ch) // 2
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)
w = round(a.height * aw / ah / 2) * 2
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a.start), "-t", str(a.dur), "-i", a.src, "-vf",
    f"fps={a.fps},crop={cw}:{ch}:{x}:{y},scale={w}:{a.height}:flags=lanczos", "-q:v", "3",
    str(out / "%04d.jpg")], check=True)
n = len(list(out.glob("*.jpg")))
print(f"{out}/  {n} frames  {w}x{a.height}  crop {cw}x{ch} at x={x}  (in the scene: ['footage/{a.name}', {n}])")
