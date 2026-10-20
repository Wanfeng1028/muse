"""Two-pass loudnorm of a narration master to YouTube/IG level.

    python engine/loudnorm.py <in.wav> <out.m4a> [--lufs -14]

linear=true applies one static gain, so word timings (and every animation keyed to them)
never shift. ffmpeg prints the analysis on stderr, so read stderr, not stdout.
"""
import json, re, subprocess, sys

src, out = sys.argv[1], sys.argv[2]
lufs = float(sys.argv[sys.argv.index("--lufs") + 1]) if "--lufs" in sys.argv else -14.0
target = f"I={lufs}:TP=-1.5:LRA=11"

p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-af", f"loudnorm={target}:print_format=json",
                    "-f", "null", "-"], capture_output=True, text=True, encoding="utf8", errors="replace")
m = json.loads(re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr)[-1])
af = (f"loudnorm={target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
      f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-af", af, "-ac", "2",
                "-c:a", "aac", "-b:a", "192k", out], check=True)
p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", out, "-af", "ebur128=peak=true", "-f", "null", "-"],
                   capture_output=True, text=True, encoding="utf8", errors="replace")
summary = p.stderr[p.stderr.rfind("Summary:"):]
i = re.search(r"I:\s+(-?[\d.]+) LUFS", summary).group(1)
tp = re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary).group(1)
print(f"{out}: {i} LUFS integrated, true peak {tp} dBFS (input was {m['input_i']} LUFS)")
