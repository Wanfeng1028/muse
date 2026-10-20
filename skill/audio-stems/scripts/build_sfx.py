#!/usr/bin/env python3
"""
Place SFX clips on a timeline → one synced SFX track (silent base + clips at exact times).

events.json:  { "total": 161.0, "events": [ {"t": 20.02, "clip": "whoosh", "gain": 0.7}, ... ] }
clips dir:    contains <clip>.mp3 for each clip name referenced.

Usage:
  python3 build_sfx.py events.json clips_dir out.mp3
"""
import sys, json, os, subprocess

def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    spec = json.load(open(sys.argv[1])); clips = sys.argv[2]; out = sys.argv[3]
    total = float(spec["total"]); ev = spec["events"]
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-t", str(total),
           "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    fc, mix = [], ["[0:a]"]
    for i, e in enumerate(ev):
        path = os.path.join(clips, e["clip"] + ".mp3")
        if not os.path.exists(path):
            sys.exit(f"missing clip: {path}")
        cmd += ["-i", path]
        idx = i + 1; ms = int(round(float(e["t"]) * 1000)); g = float(e.get("gain", 0.7))
        fc.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,"
                  f"adelay={ms}:all=1,volume={g}[a{idx}]")
        mix.append(f"[a{idx}]")
    fc.append("".join(mix) + f"amix=inputs={len(ev)+1}:normalize=0:dropout_transition=0[mx]")
    fc.append("[mx]alimiter=limit=0.95[out]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[out]", "-t", str(total),
            "-c:a", "libmp3lame", "-b:a", "192k", out, "-loglevel", "error"]
    rc = subprocess.run(cmd).returncode
    print("OK" if rc == 0 else "FAILED", out, f"({len(ev)} events)")

if __name__ == "__main__":
    main()
