#!/usr/bin/env python3
"""Transcribe a voice recording locally with word-level timestamps.

Writes words.json (every word with start/end) and transcript.txt, one phrase per line as
`[start] word@time word@time …` — the per-word times are what shots are cut to.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


PHRASE_MAX_WORDS = 5
CONFIG_PATH = Path(os.environ.get(
    "VV_CONFIG",
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "shenghua" / "config.json",
))


def load_config() -> dict:
    """User defaults; CLI flags override them. A corrupt file fails loud rather than being ignored."""
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        print(f"Cannot read {CONFIG_PATH}: {error}", file=sys.stderr)
        print('Next: fix the JSON, e.g. {"whisper": {"model": "large-v3", "device": "cuda"}}', file=sys.stderr)
        raise SystemExit(1)


def cuda_available() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def resolve_model(value: str) -> str:
    """A local CTranslate2 folder is used as-is (no download); anything else is a faster-whisper name."""
    path = Path(value).expanduser()
    if path.is_dir():
        return str(path)
    if path.exists() or value.startswith(("/", "./", "../", "~")):
        print(f"Not a CTranslate2 model folder: {value}", file=sys.stderr)
        print("Next: pass a faster-whisper model name (e.g. large-v3) or a converted CTranslate2 folder", file=sys.stderr)
        raise SystemExit(1)
    return value


def whisper_settings(cli_model, cli_device, cli_compute, default_model):
    """CLI flag > config.json > built-in default, with auto device/compute resolved."""
    cfg = load_config().get("whisper", {})
    model = cli_model or cfg.get("model") or default_model
    device = cli_device or cfg.get("device") or "auto"
    compute = cli_compute or cfg.get("compute_type") or "auto"
    if device == "auto":
        device = "cuda" if cuda_available() else "cpu"
    elif device == "cuda" and not cuda_available():
        print("device 'cuda' requested but no CUDA GPU is available", file=sys.stderr)
        print("Next: pass --device cpu (or auto), or install a CUDA build of ctranslate2", file=sys.stderr)
        raise SystemExit(1)
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    return resolve_model(model), device, compute


def probe_duration(audio: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def split_phrases(words):
    phrases, current = [], []
    for word in words:
        current.append(word)
        if len(current) >= PHRASE_MAX_WORDS or word["t"][-1] in ".,?!":
            phrases.append(current)
            current = []
    if current:
        phrases.append(current)
    return phrases


def main() -> int:
    parser = argparse.ArgumentParser(description="Word-level transcription with faster-whisper.")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--model", default=None,
                        help="faster-whisper model name (tiny, base, small, medium, large-v3, large-v3-turbo, "
                             "distil-large-v3, …) or a local CTranslate2 model folder; default: config.json, else small")
    parser.add_argument("--device", default=None, choices=["auto", "cpu", "cuda"],
                        help="default: config.json, else auto (cuda when a GPU is present)")
    parser.add_argument("--compute-type", default=None,
                        help="e.g. int8, float16, float32; default: config.json, else auto (float16 on cuda, int8 on cpu)")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--vocab", default="", help="comma-separated names and terms the speaker uses, to bias recognition")
    args = parser.parse_args()

    if not args.audio.is_file():
        print(f"No such audio file: {args.audio}", file=sys.stderr)
        print("Next: pass a path to an existing audio or video file", file=sys.stderr)
        return 1

    args.outdir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(args.audio)
    model_name, device, compute_type = whisper_settings(args.model, args.device, args.compute_type, "small")

    from faster_whisper import WhisperModel

    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(args.audio), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
            check=True,
        )
        try:
            model = WhisperModel(model_name, device=device, compute_type=compute_type, cpu_threads=args.threads)
        except Exception as error:
            print(f"Cannot load the '{model_name}' model: {error}", file=sys.stderr)
            print("Next: check the model name or folder, or run setup.sh to fetch a model", file=sys.stderr)
            return 1
        segments, info = model.transcribe(
            str(wav), beam_size=5, word_timestamps=True, vad_filter=False,
            initial_prompt=args.vocab or None,
        )
        words = [
            {"t": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)}
            for segment in segments for w in (segment.words or []) if w.word.strip()
        ]
    elapsed = time.time() - started

    if not words:
        print("0 words — no speech detected.", file=sys.stderr)
        print(f"Next: check the audio with `ffplay {args.audio}`", file=sys.stderr)
        return 1

    words_path = args.outdir / "words.json"
    transcript_path = args.outdir / "transcript.txt"
    words_path.write_text(json.dumps(words), encoding="utf-8")
    phrases = split_phrases(words)
    with transcript_path.open("w", encoding="utf-8") as handle:
        for phrase in phrases:
            handle.write(f"[{phrase[0]['s']:.2f}] " + " ".join(f"{w['t']}@{w['s']:.2f}" for w in phrase) + "\n")

    print(
        f"Transcribed {duration:.1f}s → {len(words)} words · {len(phrases)} phrases · "
        f"lang={info.language} · {elapsed:.0f}s elapsed ({duration / elapsed:.1f}x realtime) · "
        f"{model_name} on {device}/{compute_type}"
    )
    print(f"  {words_path}")
    print(f"  {transcript_path}")
    print(f"Next: proofread {transcript_path.name}, write fixes.json, run build_captions.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
