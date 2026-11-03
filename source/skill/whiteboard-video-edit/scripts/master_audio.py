"""Master a rough cut's PCM to about -14 LUFS with the true peak held at -3 dBTP on the WAV (AAC adds
up to about 1.5 dB on the encode):
pre gain to -26.6 LUFS (the level the compressor was tuned at), acompressor (threshold -28 dB, 2.5:1),
make up gain, 4x oversampled alimiter at -3 dBTP with latency=1 (without it the limiter delays the
audio by its attack time), back to 48 kHz. The make up gain is solved in two passes.
Usage: python3 master_audio.py <rough_cut_master.mov> <out.wav>"""
import json, re, subprocess, sys
src, out = sys.argv[1], sys.argv[2]
from pathlib import Path
Path(out).parent.mkdir(parents=True, exist_ok=True)


def loud(args):
    p = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner"] + args + ["-af" if "-af" not in args else "-f", "ebur128=peak=true" if "-af" not in args else "null", "-f", "null", "-"],
                       capture_output=True, text=True)
    s = p.stderr[p.stderr.rfind("Summary"):]
    I = float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1))
    tp = float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", s).group(1))
    return I, tp


def measure(path):
    p = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    s = p.stderr[p.stderr.rfind("Summary"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", s).group(1))


I0, tp0 = measure(src)
pre = -26.6 - I0
comp = f"volume={pre:.2f}dB,acompressor=threshold=-28dB:ratio=2.5:attack=10:release=120"
chain = lambda g: f"{comp},volume={g:.2f}dB,aresample=192000,alimiter=limit=0.708:level=disabled:attack=5:release=50:latency=1,aresample=48000"
g = 12.6  # first guess
for _ in range(3):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-map", "0:a:0", "-af", chain(g), "-c:a", "pcm_s24le", "-ar", "48000", out], check=True)
    I, tp = measure(out)
    if abs(I + 14.0) <= 0.1:
        break
    g += -14.0 - I
print(json.dumps({"source_I": I0, "source_tp": tp0, "pre_gain_db": round(pre, 2), "makeup_db": round(g, 2), "wav_I": I, "wav_tp": tp,
                  "chain": chain(g)}))
