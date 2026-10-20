"""Word timings for every voice clip (local faster-whisper, loads once).

    python engine/align.py <vo_dir>

Reads <vo_dir>/*.wav, writes <vo_dir>/words.json {id: [{w, s, e}, ...]} with times relative
to the clip start. Set HF_HOME to choose where the whisper model is cached.
"""
import glob, json, os, sys
from faster_whisper import WhisperModel

vo = sys.argv[1]
model = WhisperModel("small.en", device="cpu", compute_type="int8")
out = {}
for f in sorted(glob.glob(os.path.join(vo, "b*.wav"))):
    bid = os.path.splitext(os.path.basename(f))[0]
    segs, _ = model.transcribe(f, word_timestamps=True, language="en", beam_size=5)
    words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in s.words]
    out[bid] = words
    print(bid, len(words), " ".join(w["w"] for w in words)[:90], flush=True)
json.dump(out, open(os.path.join(vo, "words.json"), "w"), indent=0)
print("done", len(out))
