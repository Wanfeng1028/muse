"""Batch Kokoro TTS: load the model once, speak every beat.

    python engine/tts.py <lines.json> <outdir> [--voice af_heart] [--speed 1.0]

lines.json = [{"id": "b01", "say": "text to speak"}, ...]
Writes <outdir>/<id>.wav (24 kHz mono) and <outdir>/durations.json {id: seconds}.
Same model + voices as `hyperframes tts` (~/.cache/hyperframes/tts), but ~18x faster on a
60-beat episode because the model loads once instead of once per line.
"""
import json, os, sys, time
import kokoro_onnx
import soundfile as sf

args = sys.argv[1:]
lines_path, outdir = args[0], args[1]
voice = args[args.index("--voice") + 1] if "--voice" in args else "af_heart"
speed = float(args[args.index("--speed") + 1]) if "--speed" in args else 1.0

cache = os.path.join(os.path.expanduser("~"), ".cache", "hyperframes", "tts")
model = kokoro_onnx.Kokoro(os.path.join(cache, "models", "kokoro-v1.0.onnx"),
                           os.path.join(cache, "voices", "voices-v1.0.bin"))
os.makedirs(outdir, exist_ok=True)
lines = json.load(open(lines_path, encoding="utf8"))
dp = os.path.join(outdir, "durations.json")
durs = json.load(open(dp)) if os.path.exists(dp) else {}  # partial re-runs merge
t0 = time.time()
for ln in lines:
    samples, rate = model.create(ln["say"], voice=voice, speed=speed, lang="en-us")
    sf.write(os.path.join(outdir, ln["id"] + ".wav"), samples, rate)
    durs[ln["id"]] = round(len(samples) / rate, 3)
    print(f'{ln["id"]} {durs[ln["id"]]:6.2f}s  {ln["say"][:60]}', flush=True)
json.dump(durs, open(dp, "w"), indent=1)
print(f"done: {len(lines)} lines, {sum(durs[l['id']] for l in lines):.1f}s of speech, {time.time() - t0:.0f}s wall")
