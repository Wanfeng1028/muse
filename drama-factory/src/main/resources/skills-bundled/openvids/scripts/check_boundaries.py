import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np


def pixels(path):
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True,
    )
    width, height = map(int, probe.stdout.strip().split(",")[:2])
    return np.frombuffer(result.stdout, np.uint8).reshape(height, width, 3).astype(np.int16)


def main():
    parser = argparse.ArgumentParser(description="Render and compare adjacent scene handoff frames. Requires Node 24+, npx, and ffmpeg.")
    parser.add_argument("projectDir", type=Path)
    args = parser.parse_args()
    project = args.projectDir.resolve()
    if not (project / "src/timeline.ts").is_file() or not (project / "src/index.ts").is_file():
        parser.error("projectDir must contain src/timeline.ts and src/index.ts.")
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        raise RuntimeError("npx is not on PATH.")
    module = (project / "src/timeline.ts").as_uri()
    code = f"const t=await import({json.dumps(module)});console.log(JSON.stringify(t.SCENES));"
    result = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True)
    scenes = json.loads(result.stdout)
    if not isinstance(scenes, list) or len(scenes) < 2:
        raise RuntimeError("Expected at least two scenes.")
    ids = set()
    for scene in scenes:
        if not isinstance(scene, dict) or not isinstance(scene.get("id"), str) or \
                scene["id"] in ids or not isinstance(scene.get("dur"), int) or scene["dur"] <= 0:
            raise RuntimeError("Each scene needs a unique string id and a positive integer dur.")
        ids.add(scene["id"])
    failures = 0
    with tempfile.TemporaryDirectory(prefix="openvids-boundaries-") as temporary:
        for index, (left, right) in enumerate(zip(scenes, scenes[1:])):
            images = []
            for side, scene, frame in [("last", left, left["dur"] - 1), ("first", right, 0)]:
                output = Path(temporary) / f"{index}-{side}.png"
                rendered = subprocess.run(
                    [npx, "--no-install", "remotion", "still", "src/index.ts", scene["id"], str(output),
                     f"--frame={frame}", "--log=error"], cwd=project, capture_output=True, text=True,
                )
                if rendered.returncode:
                    raise RuntimeError(f"Render {scene['id']} frame {frame} failed:\n{rendered.stdout}\n{rendered.stderr}")
                images.append(pixels(output))
            if images[0].shape != images[1].shape:
                raise RuntimeError(f"Boundary dimensions differ: {left['id']} to {right['id']}.")
            diff = np.abs(images[0] - images[1]).max(axis=2)
            maximum = int(diff.max())
            differing = int(np.count_nonzero(diff))
            budget = math.floor(diff.size * 0.0001)
            passed = maximum <= 8 and differing <= budget
            failures += not passed
            print(f"{left['id']}[{left['dur'] - 1}] -> {right['id']}[0]: "
                  f"max diff {maximum}/255, differing pixels {differing}/{diff.size}, "
                  f"tolerance <=8 on <={budget} pixels  {'PASS' if passed else 'FAIL'}")
    print(f"{len(scenes) - 1} boundaries, {failures} failures")
    return int(failures > 0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
