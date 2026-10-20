#!/usr/bin/env python3
"""Voice a script with one synthetic voice per character, on this machine.

  speak.py <script.txt> <work-dir> [--cast cast.json] [--narrator NAME] [--gap S] [--scene-gap S]
           [--align-model NAME | --no-align] [--device auto|cpu|cuda] [--compute-type T]

Script format, one spoken line per line:

  Keeper: Meet Pip. Pip carries messages between five services.
  Pip: Which wire goes where?!
  ---                      scene break: a longer pause
  (pause 1.2)              explicit silence in seconds
  A line with no name belongs to the narrator (--narrator, else the first speaker).
  # comments are skipped

Writes <work>/voice.wav (the recording the rest of the workflow uses), <work>/speech.json and
<work>/speech.js (who speaks when, read by the template's hosts), <work>/words.json and
transcript.txt (word times in transcribe.py's format), and <work>/script.txt. The voiced track is
aligned with faster-whisper, so the script's own words get the times they are spoken at.

The voice model downloads once with setup.sh --voices; after that it runs offline. The alignment
model is any faster-whisper name or a local CTranslate2 folder; --device/--compute-type and the
"whisper" section of ~/.config/shenghua/config.json apply to it as in transcribe.py.
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

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

MODEL_DIR = Path(os.environ.get("VV_KOKORO_DIR", Path.home() / ".cache" / "shenghua" / "kokoro"))
MODEL, VOICES = "kokoro-v1.0.onnx", "voices-v1.0.bin"
SR_OUT = 48000
# First speaker gets the first voice, and so on; a pitch above 1 makes a small, squeaky character
DEFAULT_VOICES = [
    {"voice": "af_heart"},
    {"voice": "am_puck", "pitch": 1.32, "speed": 1.05},
    {"voice": "am_michael"},
    {"voice": "bf_emma"},
    {"voice": "am_fenrir"},
    {"voice": "af_nova"},
]
SPEAKER = re.compile(r"^([A-Za-z][\w'-]*(?: [A-Za-z][\w'-]*)?)\s*:\s*(.+)$")
PAUSE = re.compile(r"^\(pause\s+([0-9.]+)\)$", re.I)
# Real lines, even noisy or pitched, average ≥0.62 over matched words; below this the times were worse than estimates
MIN_PROBABILITY = 0.55


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse(text, cast, narrator):
    items, speakers = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "---":
            items.append(("scene", None, None))
            continue
        pause = PAUSE.match(line)
        if pause:
            items.append(("pause", float(pause.group(1)), None))
            continue
        match = SPEAKER.match(line)
        # Only a known cast name, or a short name when there is no cast file, counts as a speaker
        if match and (slug(match.group(1)) in cast or not cast):
            who, words = slug(match.group(1)), match.group(2).strip()
        else:
            who, words = narrator, line
        if who is None:
            print(f"Line has no speaker and no narrator is set: {line[:60]}", file=sys.stderr)
            return None, None
        if who not in speakers:
            speakers.append(who)
        items.append(("line", who, words))
    return items, speakers


def trim(audio, threshold=0.01):
    loud = np.where(np.abs(audio) > threshold)[0]
    if len(loud) == 0:
        return audio
    return audio[max(0, loud[0] - 400): loud[-1] + 800]


def to_48k(audio, sr, pitch):
    # ffmpeg resamples and pitch-shifts in one pass; pitch keeps the pace close to natural
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.wav", Path(tmp) / "out.wav"
        write_wav(src, audio, sr)
        chain = f"aresample={SR_OUT}"
        if pitch != 1.0:
            chain = f"asetrate={int(sr * pitch)},aresample={SR_OUT},atempo={1 / pitch * 1.08:.4f}"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", chain, "-ac", "1", str(dst)], check=True)
        with wave.open(str(dst)) as handle:
            return np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16).astype(np.float32) / 32767


def word_times(words, s, e):
    """Spread a line's words over its audio by length; punctuation adds the pause a voice leaves there."""
    tokens = words.split()
    weights = [len(w.strip(".,!?;:\"'()")) + 2 for w in tokens]
    pauses = [4 if w[-1] in ".!?" else 2.5 if w[-1] in ",;:" else 0 for w in tokens]
    unit = (e - s) / (sum(weights) + sum(pauses[:-1]) or 1)
    out, t = [], s
    for w, weight, pause in zip(tokens, weights, pauses):
        out.append({"t": w, "s": round(t, 2), "e": round(t + weight * unit, 2)})
        t += (weight + pause) * unit
    return out


def normalise(token):
    return re.sub(r"[^\w]", "", token.lower())


def recognise(model, voice, language=None):
    """Every word faster-whisper hears in the whole voice track, with times in the track."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "voice.wav"
        write_wav(path, voice, SR_OUT)
        # No prompt: a prompt of the script is echoed back over audio that says nothing
        segments, _ = model.transcribe(
            str(path), beam_size=1, temperature=0.0, word_timestamps=True, vad_filter=False, language=language,
        )
        return [w for segment in segments for w in (segment.words or []) if normalise(w.word)]


def align_line(heard, text, s, e):
    """Time the script's own tokens from the words heard inside [s, e]; None when they don't match the line."""
    inside = [w for w in heard if s <= (w.start + w.end) / 2 <= e]
    tokens = text.split()
    keys = [normalise(w) for w in tokens]
    matcher = difflib.SequenceMatcher(None, keys, [normalise(w.word) for w in inside], autojunk=False)
    times, confidence = [None] * len(tokens), []
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            word = inside[block.b + k]
            times[block.a + k] = (word.start, word.end)
            confidence.append(word.probability)
    spoken = [i for i, key in enumerate(keys) if key]
    if not confidence or len(confidence) * 2 < len(spoken) or sum(confidence) / len(confidence) < MIN_PROBABILITY:
        return None

    # Unmatched tokens share the gap between their matched neighbours by length, as word_times() does
    i = 0
    while i < len(tokens):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(tokens) and times[j] is None:
            j += 1
        start = times[i - 1][1] if i > 0 else s
        end = times[j][0] if j < len(tokens) else e
        weights = [len(keys[k]) + 2 for k in range(i, j)]
        unit = max(end - start, 0.0) / sum(weights)
        cursor = start
        for k, weight in zip(range(i, j), weights):
            times[k] = (cursor, cursor + weight * unit)
            cursor += weight * unit
        i = j

    out, last = [], s
    for token, (ws, we) in zip(tokens, times):
        start = min(max(ws, last), e)
        end = min(max(we, start), e)
        out.append({"t": token, "s": round(start, 2), "e": round(end, 2)})
        last = start
    return out


def split_phrases(words):
    """Mirrors transcribe.split_phrases, so transcript.txt reads the same either way."""
    phrases, current = [], []
    for word in words:
        current.append(word)
        if len(current) >= 5 or word["t"][-1] in ".,?!":
            phrases.append(current)
            current = []
    if current:
        phrases.append(current)
    return phrases


def write_wav(path, data, sr):
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(pcm.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("--cast", type=Path, default=None, help='{"pip": {"voice": "am_puck", "pitch": 1.32, "speed": 1.05}}')
    parser.add_argument("--narrator", default=None, help="speaker for lines without a name")
    parser.add_argument("--gap", type=float, default=0.25, help="silence between lines")
    parser.add_argument("--scene-gap", type=float, default=0.7, help="silence at a --- scene break")
    parser.add_argument("--lead", type=float, default=0.4, help="silence before the first line")
    parser.add_argument("--align-model", default=None,
                        help="faster-whisper model name or local CTranslate2 folder that times each line's words; "
                             "default: config.json, else base")
    parser.add_argument("--device", default=None, choices=["auto", "cpu", "cuda"],
                        help="alignment device; default: config.json, else auto (cuda when a GPU is present)")
    parser.add_argument("--compute-type", default=None,
                        help="alignment compute type, e.g. int8, float16; default: config.json, else auto")
    parser.add_argument("--no-align", action="store_true", help="estimate word times from word length instead (fast draft)")
    args = parser.parse_args()

    if not args.script.is_file():
        print(f"No such script: {args.script}", file=sys.stderr)
        print("Next: write the script as 'Name: line' lines and pass its path", file=sys.stderr)
        return 1
    try:
        from kokoro_onnx import Kokoro
    except ImportError:
        print("kokoro-onnx is not installed", file=sys.stderr)
        print("Next: run setup.sh --voices", file=sys.stderr)
        return 1
    if not (MODEL_DIR / MODEL).is_file() or not (MODEL_DIR / VOICES).is_file():
        print(f"Voice model missing in {MODEL_DIR}", file=sys.stderr)
        print("Next: run setup.sh --voices (downloads ~350 MB once)", file=sys.stderr)
        return 1
    cast = {}
    if args.cast:
        try:
            cast = {slug(k): v for k, v in json.loads(args.cast.read_text(encoding="utf-8")).items()}
        except (OSError, json.JSONDecodeError) as e:
            print(f"Cannot read cast file {args.cast}: {e}", file=sys.stderr)
            print('Next: fix the JSON, e.g. {"keeper": {"voice": "af_heart"}}', file=sys.stderr)
            return 1

    text = args.script.read_text(encoding="utf-8")
    narrator = slug(args.narrator) if args.narrator else None
    if narrator is None:
        first = next((SPEAKER.match(l.strip()) for l in text.splitlines() if SPEAKER.match(l.strip())), None)
        narrator = slug(first.group(1)) if first else "narrator"
    items, speakers = parse(text, cast, narrator)
    if items is None:
        print("Next: add a 'Name:' to that line or pass --narrator", file=sys.stderr)
        return 1
    if not speakers:
        print(f"No spoken lines in {args.script}", file=sys.stderr)
        print("Next: write lines as 'Name: what they say'", file=sys.stderr)
        return 1

    tts = Kokoro(str(MODEL_DIR / MODEL), str(MODEL_DIR / VOICES))
    available = set(tts.get_voices())
    for i, who in enumerate(speakers):
        cast.setdefault(who, DEFAULT_VOICES[i % len(DEFAULT_VOICES)])
        if cast[who].get("voice") not in available:
            print(f"Unknown voice '{cast[who].get('voice')}' for {who}", file=sys.stderr)
            print(f"Next: pick one of {', '.join(sorted(available))}", file=sys.stderr)
            return 1

    aligner, align_seconds = None, 0.0
    if not args.no_align:
        # One thread: CTranslate2's threaded MKL kernels shift a word by a frame between runs; ~5% slower
        os.environ["OMP_NUM_THREADS"] = os.environ["MKL_NUM_THREADS"] = "1"
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            print("faster-whisper is not installed; it aligns word times to the voices", file=sys.stderr)
            print("Next: run setup.sh, or pass --no-align for estimated word times", file=sys.stderr)
            return 1
        started = time.time()
        model_name, device, compute_type = whisper_settings(args.align_model, args.device, args.compute_type, "base")
        # A missing download or a broken cache surfaces as several library error types
        try:
            aligner = WhisperModel(model_name, device=device, compute_type=compute_type, cpu_threads=1)
        except Exception as error:
            print(f"Cannot load the '{model_name}' alignment model: {error}", file=sys.stderr)
            print("Next: run setup.sh --voices, or pass --no-align", file=sys.stderr)
            return 1
        align_seconds = time.time() - started

    parts, speech, t = [np.zeros(int(SR_OUT * args.lead), dtype=np.float32)], [], args.lead
    for kind, a, b in items:
        if kind in ("scene", "pause"):
            seconds = args.scene_gap if kind == "scene" else a
            parts.append(np.zeros(int(SR_OUT * seconds), dtype=np.float32))
            t += seconds
            continue
        who, text = a, b
        spec = cast[who]
        audio, sr = tts.create(text, voice=spec["voice"], speed=float(spec.get("speed", 1.0)), lang=spec.get("lang", "en-us"))
        audio = to_48k(trim(np.asarray(audio, dtype=np.float32)), sr, float(spec.get("pitch", 1.0)))
        d = len(audio) / SR_OUT
        line = {"i": len(speech), "who": who, "s": round(t, 3), "e": round(t + d, 3), "text": text}
        speech.append(line)
        parts += [audio, np.zeros(int(SR_OUT * args.gap), dtype=np.float32)]
        t += d + args.gap

    voice = np.concatenate(parts)
    voice *= 0.9 / (np.max(np.abs(voice)) or 1.0)
    heard = []
    if aligner is not None:
        started = time.time()
        english = all(cast[w].get("lang", "en-us").startswith("en") for w in speakers)
        heard = recognise(aligner, voice, "en" if english else None)
        align_seconds += time.time() - started
    words, estimated = [], []
    for line in speech:
        timed = align_line(heard, line["text"], line["s"], line["e"]) if aligner is not None else None
        if aligner is not None and timed is None:
            estimated.append(f"{line['who']} line {line['i'] + 1}")
        words += timed or word_times(line["text"], line["s"], line["e"])
    args.work.mkdir(parents=True, exist_ok=True)
    write_wav(args.work / "voice.wav", voice, SR_OUT)
    (args.work / "speech.json").write_text(json.dumps(speech, indent=1), encoding="utf-8")
    (args.work / "speech.js").write_text("window.SPEECH=" + json.dumps(speech) + ";", encoding="utf-8")
    (args.work / "script.txt").write_text("\n".join(x["text"] for x in speech) + "\n", encoding="utf-8")
    (args.work / "cast.json").write_text(json.dumps(cast, indent=1), encoding="utf-8")
    # Same shape transcribe.py writes, so build_captions.py runs without a transcription pass
    (args.work / "words.json").write_text(json.dumps(words), encoding="utf-8")
    with (args.work / "transcript.txt").open("w", encoding="utf-8") as handle:
        for phrase in split_phrases(words):
            handle.write(f"[{phrase[0]['s']:.2f}] " + " ".join(f"{w['t']}@{w['s']:.2f}" for w in phrase) + "\n")

    end = speech[-1]["e"]
    voices = " · ".join(f"{w}={cast[w]['voice']}" + (f"@{cast[w]['pitch']}" if cast[w].get("pitch") else "") for w in speakers)
    if aligner is None:
        timing = "estimated word times (--no-align)"
    else:
        timing = f"{len(speech) - len(estimated)}/{len(speech)} lines aligned in {align_seconds:.1f}s"
        if estimated:
            timing += f" ({len(estimated)} estimated: {', '.join(estimated)})"
    print(f"voice.wav · {len(speech)} lines · {end:.1f}s · {voices} · {timing}")
    print(f"Next: run build_captions.py {args.work} (composition duration ≈ {end + 2.5:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
