#!/usr/bin/env python
"""Local ASR via faster-whisper -> word-level transcript JSON (UTF-8).

Usage:
  python transcribe.py <audio-or-video> <out.json> [--lang fr] [--model small]

Emits:
  {
    "language": "fr",
    "language_probability": 0.99,
    "duration": 10.5,
    "words":    [{"text": "Bonjour,", "start": 0.0, "end": 0.68}, ...],
    "segments": [{"start": 0.0, "end": 2.4, "text": "Bonjour, ceci est un test."}, ...]
  }

Notes:
  - CPU int8 by default (works everywhere, no GPU needed).
  - lang="auto" lets whisper detect (slightly less reliable); default "fr".
  - Model download is cached under ~/.cache/huggingface on first use.
"""
import sys, json, argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("out")
    ap.add_argument("--lang", default="fr", help="fr | en | auto")
    ap.add_argument("--model", default="small",
                    help="tiny|base|small|medium|large-v3 (multilingual)")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    lang = None if a.lang == "auto" else a.lang
    segs, info = model.transcribe(a.input, language=lang, word_timestamps=True,
                                  vad_filter=True)

    words, segments = [], []
    max_end = 0.0
    for s in segs:
        segments.append({"start": round(s.start, 3), "end": round(s.end, 3),
                         "text": s.text.strip()})
        for w in (s.words or []):
            t = (w.word or "").strip()
            if not t:
                continue
            words.append({"text": t, "start": round(w.start, 3),
                          "end": round(w.end, 3)})
            max_end = max(max_end, w.end)

    out = {
        "language": info.language,
        "language_probability": round(float(info.language_probability), 3),
        "duration": round(max_end, 3),
        "words": words,
        "segments": segments,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    sys.stderr.write(f"transcribed: lang={out['language']} "
                     f"words={len(words)} -> {a.out}\n")

if __name__ == "__main__":
    main()
