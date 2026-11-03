"""Lay every voice clip at its beat start -> one master narration track.

    python engine/mix.py <beats.json> <vo_dir> <total_seconds> <out.wav>

beats.json comes from the voiced build (start times already include the clip lengths).
Output is 48 kHz stereo WAV, un-normalised; loudness is set afterwards with ffmpeg loudnorm.
"""
import json, os, sys
import numpy as np
import soundfile as sf

beats_path, vo, total, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
SR = 48000
beats = json.load(open(beats_path, encoding="utf8"))
track = np.zeros(int(total * SR) + SR, dtype=np.float32)
for b in beats:
    x, sr = sf.read(os.path.join(vo, b["id"] + ".wav"), dtype="float32")
    if x.ndim > 1: x = x.mean(axis=1)
    if sr != SR:  # linear resample 24k -> 48k is fine for speech at this level
        n = int(len(x) * SR / sr)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
    i = int(round(b["start"] * SR))
    track[i:i + len(x)] += x[: len(track) - i]
track = track[: int(total * SR)]
sf.write(out, np.stack([track, track], axis=1), SR, subtype="PCM_16")
print(f"master: {total:.2f}s, {len(beats)} clips, peak {np.abs(track).max():.3f}")
