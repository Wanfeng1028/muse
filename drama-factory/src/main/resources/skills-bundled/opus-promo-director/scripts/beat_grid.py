"""Plan a beat grid so every cut lands on a whole frame, and write a shot list skeleton.

Usage:
  python beat_grid.py --fps 30 --seconds 20
      list BPMs (90-180) whose beat is a whole number of frames at this fps
  python beat_grid.py --bpm 128
      for an existing song: list common fps values where this BPM gives whole-frame beats
  python beat_grid.py --fps 30 --bpm 150 --seconds 20 --cuts 4,4,2,2,2,1,1,8
      scene lengths in beats -> start frame, time and length of each scene
  add --json to print the plan as JSON
  add --shotlist production/shotlist.json to write a shot list skeleton to fill in
  add --names hook,problem,... to name the scenes

When the beat is not a whole number of frames, each cut is rounded to the nearest frame from the
song start, so the error never builds up past half a frame.
"""
import argparse, json, os, sys

COMMON_FPS = [24, 25, 30, 32, 48, 50, 60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--bpm", type=float)
    ap.add_argument("--cuts", help="comma separated scene lengths in beats")
    ap.add_argument("--names", help="comma separated scene names")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--shotlist", help="write a shot list skeleton to this path")
    a = ap.parse_args()

    if a.bpm is not None and a.fps is None and not a.cuts:
        print(f"{a.bpm:g} BPM: frames per beat at common fps")
        for fps in COMMON_FPS:
            fpb = fps * 60 / a.bpm
            mark = "whole" if abs(fpb - round(fpb)) < 1e-9 else "drifts, rounded per cut"
            print(f"  {fps:2d} fps -> {fpb:.3f} frames/beat ({mark})")
        return

    fps = a.fps or 30
    if a.bpm is None:
        print(f"BPMs with a whole-frame beat at {fps}fps (range 90-180):")
        for bpm in range(90, 181):
            fpb = fps * 60 / bpm
            if abs(fpb - round(fpb)) < 1e-9:
                print(f"  {bpm:3d} BPM = {int(round(fpb)):2d} frames/beat, {a.seconds * bpm / 60:.1f} beats in {a.seconds:g}s")
        return

    fpb = fps * 60 / a.bpm
    whole = abs(fpb - round(fpb)) < 1e-9
    if not whole:
        print(f"note: {a.bpm:g} BPM is {fpb:.3f} frames/beat at {fps}fps. Cuts are rounded per beat from the song start. "
              f"Run with only --bpm to see fps values that divide evenly.", file=sys.stderr)
    total_frames = round(a.seconds * fps)
    total_beats = total_frames / fpb
    if not a.cuts:
        print(f"{a.bpm:g} BPM, {fpb:g} frames/beat, {total_beats:.2f} beats in {total_frames} frames")
        return

    lengths = [float(x) for x in a.cuts.split(",")]
    names = a.names.split(",") if a.names else []
    scenes, beat = [], 0.0
    for i, n in enumerate(lengths):
        start = round(beat * fpb)
        end = round((beat + n) * fpb)
        scenes.append({
            "name": names[i] if i < len(names) else f"scene{i + 1}",
            "startBeat": beat, "beats": n, "from": start, "durationInFrames": end - start,
            "startSec": round(start / fps, 3),
        })
        beat += n
    used = round(beat * fpb)
    plan = {"fps": fps, "bpm": a.bpm, "framesPerBeat": fpb, "totalFrames": total_frames, "scenes": scenes}

    if a.shotlist:
        shot = dict(plan)
        shot["scenes"] = [dict(s, content="", text="", transition="", sound="", source="") for s in scenes]
        os.makedirs(os.path.dirname(os.path.abspath(a.shotlist)), exist_ok=True)
        with open(a.shotlist, "w", encoding="utf-8") as f:
            json.dump(shot, f, ensure_ascii=False, indent=2)
        print(f"wrote {a.shotlist}", file=sys.stderr)

    if a.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print(f"{a.bpm:g} BPM, {fpb:g} frames/beat at {fps}fps")
        for s in scenes:
            print(f"  {s['name']:>10}: beat {s['startBeat']:5.1f}  frame {s['from']:4d}  "
                  f"{s['startSec']:6.2f}s  {s['beats']:g} beats = {s['durationInFrames']} frames")
        print(f"  total {used} of {total_frames} frames ({beat:g} of {total_beats:.2f} beats)")
    if used > total_frames:
        print(f"warning: scenes run {used - total_frames} frames past {a.seconds:g}s", file=sys.stderr)
    elif used < total_frames:
        print(f"note: {total_frames - used} frames left after the last scene", file=sys.stderr)


if __name__ == "__main__":
    main()
