"""Apple Vision face and body pose every 0.25 s of the rough cut (output timeline).
Usage: python3 pose_track.py <edit_dir>   (reads rough-cut/rough_cut.mp4)
Writes frames/track4/f_%05d.jpg (960x540, f_00001 = t 0.00) and frames/pose_4fps.jsonl."""
import subprocess, sys
from pathlib import Path
E = Path(sys.argv[1])
d = E / "frames/track4"
d.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(E / "rough-cut/rough_cut.mp4"), "-vf", "fps=4,scale=960:540",
                "-q:v", "3", str(d / "f_%05d.jpg")], check=True)
files = sorted(d.glob("f_*.jpg"))
pose = Path(__file__).parent / "pose"
with open(E / "frames/pose_4fps.jsonl", "w") as out:
    for i in range(0, len(files), 150):
        r = subprocess.run([str(pose)] + [str(f) for f in files[i:i + 150]], capture_output=True, text=True, check=True)
        out.write(r.stdout)
n = sum(1 for _ in open(E / "frames/pose_4fps.jsonl"))
print(f"{len(files)} frames, {n} pose rows")
