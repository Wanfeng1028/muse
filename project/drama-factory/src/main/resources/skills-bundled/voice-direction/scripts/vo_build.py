#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2", "numpy>=2"]
# ///
"""Build final VO line WAVs and word timings from chosen ElevenLabs takes (output of vo_record.py).

picks.json:
  {"lines": [
    {"line": "l01", "take": "sofia-l01b", "tempo": 1.04},
    {"line": "l06", "take": "sofia-l06b", "last_word": 9},
    {"line": "l06m", "take": "sofia-l06b", "first_word": 9},
    {"line": "l10", "take": "sofia-l10b", "spoken_fixes": {"lee": "lea"}},
    {"line": "l13", "take": "sofia-l13a", "caption_joins": [{"parts": ["acme", "punto", "com."], "text": "acme.com."}]}
  ]}
  line          output id: <out>/<line>.wav and the key in the timings
  take          take file stem in --takes (<take>.mp3 or .wav + <take>.json alignment; <take>.meta.json provenance
                from vo_record.py is copied into the timings JSON report)
  tempo         atempo factor (default 1.0). Warns outside 0.95-1.08; refused outside 0.85-1.12 unless --force
  first_word / last_word
                keep words [first_word, last_word) (0-based, tags excluded) to split one take into two lines.
                The cut snaps to the centre of the nearest measured silence (silencedetect n=-45dB:d=0.08),
                because alignment word edges can be 0.1-0.15 s late and a midpoint cut clips the word.
  spoken_fixes  {"prompt word": "spoken word"}: captions follow the audio, not the script (exact token match)
  caption_joins [{"parts": [...], "text": "..."}]: re-join words spelled out for pronunciation

Processing per line, in order: tempo, 80 Hz high-pass, split, silence trims (lead at -50 dBFS keeping 40 ms, tail at
-40 dBFS keeping 80 ms, never into an aligned word), 20 ms fade-in / 40 ms fade-out, then loudness matching to
-16 LUFS with linear gain plus a 3 ms / 15 ms limiter (max 8 dB reduction) re-measured until the true peak is at or
below -1.5 dBTP (lines under 0.6 s measured looped). Written as 48 kHz mono WAV. Word times are seconds from the start
of that line's file. Prints duration, wpm, words and syllables per second, expected vs actual duration, loudness, the
loudness spread, and lines that started 4+ LU below the median ("quiet at source": consider re-recording).
The TS module shape (export const voLines: Record<string, VoLine>) is unchanged; extra data lives in the JSON report.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pydantic import BaseModel

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _vo_build_report as report  # noqa: E402
import _voice_audio as audio  # noqa: E402
from _vo_build_process import (  # noqa: E402
    Processing,
    match_loudness,
    render,
    trim_bounds,
)

TEMPO_MIN = 0.85
TEMPO_MAX = 1.12
TEMPO_SAFE = (0.95, 1.08)
QUIET_DELTA = 4.0
TS_FIELDS = ("id", "text", "file", "duration", "wordCount", "wpm", "pace", "words")
EXAMPLE = "example: vo_build.py picks.json --takes out/vo/takes --out public/audio/vo --ts src/data/vo.generated.ts"


class CaptionJoin(BaseModel):
    parts: list[str]
    text: str


class Pick(BaseModel):
    line: str
    take: str
    tempo: float = 1.0
    first_word: int | None = None
    last_word: int | None = None
    spoken_fixes: dict[str, str] = {}
    caption_joins: list[CaptionJoin] = []


class Picks(BaseModel):
    lines: list[Pick]


Word = dict[str, str | float]
Pause = tuple[float, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Final VO WAVs + word timings from chosen takes: tempo, silence-snapped splits, fades, pace report.",
        epilog=__doc__.split("\n\n", 1)[1] + f"\n{EXAMPLE}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("picks", type=Path, help="picks JSON (schema below)")
    parser.add_argument("--takes", type=Path, default=Path("out/vo/takes"), help="take folder (default out/vo/takes)")
    parser.add_argument("--out", type=Path, default=Path("public/audio/vo"), help="WAV folder (default public/audio/vo)")
    parser.add_argument("--json", type=Path, default=Path("out/vo/vo.json"), help="timings JSON (default out/vo/vo.json)")
    parser.add_argument("--ts", type=Path, help="also write a TypeScript module, e.g. src/data/vo.generated.ts")
    parser.add_argument("--ts-name", default="voLines", help="exported const name in the TS module (default voLines)")
    parser.add_argument("--public-prefix", help="'file' field prefix for staticFile() (default: --out relative to public/)")
    parser.add_argument("--max-snap", type=float, default=0.4, help="max distance (s) from a split to a silence (default 0.4)")
    parser.add_argument("--slow", type=float, default=120, help="wpm below this is 'slow' (default 120)")
    parser.add_argument("--fast", type=float, default=170, help="wpm above this is 'fast' (default 170)")
    parser.add_argument("--force", action="store_true", help=f"allow tempo outside {TEMPO_MIN}-{TEMPO_MAX}")
    parser.add_argument("--target-lufs", type=float, default=-16.0, help="per-line loudness target (default -16)")
    parser.add_argument("--no-loudness", action="store_true", help="skip loudness matching (keep the take's level)")
    parser.add_argument("--true-peak", type=float, default=-1.5, help="max true peak per line in dBTP (default -1.5)")
    parser.add_argument("--max-limiting", type=float, default=8.0, help="max limiter reduction in dB (default 8)")
    parser.add_argument("--highpass", type=float, default=80.0, help="high-pass cutoff in Hz, 0 to disable (default 80)")
    parser.add_argument("--no-trim", action="store_true", help="keep the take's leading and trailing silence")
    parser.add_argument("--language", help="es, pt or en for syllable counts (default: the take's meta.json language)")
    parser.add_argument("--sps", type=float, default=4.5, help="syllables/s for the expected duration (default 4.5)")
    parser.add_argument("--verbose", action="store_true", help="print the ffmpeg binaries used")
    return parser.parse_args()


def detect_pauses(path: Path, total: float) -> list[Pause]:
    command = [audio.binary("ffmpeg"), "-v", "info", "-i", str(path), "-af", "silencedetect=n=-45dB:d=0.08", "-f", "null", "-"]
    log = subprocess.run(command, capture_output=True, text=True, check=False).stderr
    starts = [float(value) for value in re.findall(r"silence_start: (-?[0-9.]+)", log)]
    ends = [float(value) for value in re.findall(r"silence_end: ([0-9.]+)", log)]
    ends += [total] * (len(starts) - len(ends))
    return [(max(0.0, start), end) for start, end in zip(starts, ends)]


def words_from_alignment(alignment: dict) -> list[Word]:
    words: list[Word] = []
    current, start, end, in_tag = "", 0.0, 0.0, False
    triples = zip(alignment["characters"], alignment["character_start_times_seconds"], alignment["character_end_times_seconds"])
    for character, character_start, character_end in triples:
        if character in "[]":
            in_tag = character == "["
            continue
        if in_tag:
            continue
        if character.isspace():
            if current:
                words.append({"text": current, "start": start, "end": end})
            current = ""
            continue
        if not current:
            start = character_start
        current += character
        end = character_end
    if current:
        words.append({"text": current, "start": start, "end": end})
    return words


def scale_words(words: list[Word], tempo: float) -> list[Word]:
    return [{"text": w["text"], "start": float(w["start"]) / tempo, "end": float(w["end"]) / tempo} for w in words]


def apply_fixes(words: list[Word], pick: Pick) -> list[Word]:
    words = [{**w, "text": pick.spoken_fixes.get(str(w["text"]), w["text"])} for w in words]
    for join in pick.caption_joins:
        texts = [w["text"] for w in words]
        size = len(join.parts)
        for index in range(len(texts) - size + 1):
            if texts[index : index + size] == join.parts:
                merged = {"text": join.text, "start": words[index]["start"], "end": words[index + size - 1]["end"]}
                words = words[:index] + [merged] + words[index + size :]
                break
        else:
            print(f"  WARN {pick.line}: caption join {join.parts} not found in {texts}")
    return words


def distance_to_pause(time: float, pause: Pause) -> float:
    start, end = pause
    return 0.0 if start <= time <= end else min(abs(time - start), abs(time - end))


def split_point(words: list[Word], index: int, pauses: list[Pause], max_snap: float, line: str) -> tuple[float, str]:
    middle = (float(words[index - 1]["end"]) + float(words[index]["start"])) / 2
    if not pauses:
        return middle, f"midpoint {middle:.3f}s (no silence found)"
    nearest = min(pauses, key=lambda pause: distance_to_pause(middle, pause))
    gap = distance_to_pause(middle, nearest)
    if gap > max_snap:
        print(f"  WARN {line}: nearest silence is {gap:.2f}s from the split; cut at the midpoint, listen to it")
        return middle, f"midpoint {middle:.3f}s (nearest silence {gap:.2f}s away)"
    centre = (nearest[0] + nearest[1]) / 2
    return centre, f"silence {nearest[0]:.3f}-{nearest[1]:.3f}s centre {centre:.3f}s (word-gap midpoint {middle:.3f}s)"


def validate(pick: Pick, word_count: int, force: bool) -> None:
    if not force and not TEMPO_MIN <= pick.tempo <= TEMPO_MAX:
        sys.exit(f"error: {pick.line}: tempo {pick.tempo} outside {TEMPO_MIN}-{TEMPO_MAX} (artifacts); pass --force to allow")
    if not TEMPO_SAFE[0] <= pick.tempo <= TEMPO_SAFE[1]:
        print(f"  WARN {pick.line}: tempo {pick.tempo} outside {TEMPO_SAFE[0]}-{TEMPO_SAFE[1]}; listen for artifacts or rewrite the line")
    for name, value, lowest, highest in (("first_word", pick.first_word, 1, word_count - 1), ("last_word", pick.last_word, 1, word_count - 1)):
        if value is not None and not lowest <= value <= highest:
            sys.exit(f"error: {pick.line}: {name}={value} must be within {lowest}-{highest} ({word_count} words)")
    if pick.first_word is not None and pick.last_word is not None and pick.first_word >= pick.last_word:
        sys.exit(f"error: {pick.line}: first_word must be lower than last_word")


def take_source(takes: Path, take: str, line: str) -> Path:
    for suffix in (".mp3", ".wav"):
        if (takes / f"{take}{suffix}").is_file():
            return takes / f"{take}{suffix}"
    sys.exit(f"error: {line}: missing {takes / take}.mp3 (or .wav)")


def read_provenance(takes: Path, take: str) -> dict | None:
    path = takes / f"{take}.meta.json"
    return json.loads(path.read_text()) if path.is_file() else None


def build_line(pick: Pick, args: argparse.Namespace, settings: Processing, prefix: str, work: Path) -> dict:
    source = take_source(args.takes, pick.take, pick.line)
    alignment_path = args.takes / f"{pick.take}.json"
    if not alignment_path.is_file():
        sys.exit(f"error: {pick.line}: missing {alignment_path}")
    raw_words = words_from_alignment(json.loads(alignment_path.read_text())["alignment"])
    validate(pick, len(raw_words), args.force)
    words = apply_fixes(scale_words(raw_words, pick.tempo), pick)
    source_total = audio.probe_seconds(source)
    total = source_total / pick.tempo
    pauses = [(start / pick.tempo, end / pick.tempo) for start, end in detect_pauses(source, source_total)]
    start, end, notes = 0.0, total, []
    if pick.first_word is not None:
        start, note = split_point(scale_words(raw_words, pick.tempo), pick.first_word, pauses, args.max_snap, pick.line)
        notes.append(f"in at {note}")
    if pick.last_word is not None:
        end, note = split_point(scale_words(raw_words, pick.tempo), pick.last_word, pauses, args.max_snap, pick.line)
        notes.append(f"out at {note}")
    spoken = scale_words(raw_words, pick.tempo)[pick.first_word or 0 : pick.last_word]
    speech = (float(spoken[0]["start"]), float(spoken[-1]["start"])) if spoken else (start, start)
    start, end = trim_bounds(source, pick.tempo, start, end, speech, settings)
    target = args.out / f"{pick.line}.wav"
    staged = work / f"{pick.line}.wav"
    render(source, staged, pick.tempo, start, end, settings)
    loudness = match_loudness(staged, target, settings)
    duration = round(audio.probe_seconds(target), 3)
    shifted = shift_words(slice_words(words, raw_words, pick), start, duration)
    provenance = read_provenance(args.takes, pick.take)
    language = args.language or (provenance or {}).get("language")
    print(f"  wrote {target}")
    return {
        "id": pick.line,
        "take": pick.take,
        "tempo": pick.tempo,
        "text": " ".join(str(w["text"]) for w in shifted),
        "file": f"{prefix}/{pick.line}.wav" if prefix else f"{pick.line}.wav",
        "duration": duration,
        "wordCount": len(spoken),
        **report.pace(spoken, duration, language, args),
        "trim": [round(start, 3), round(end, 3)],
        "loudness": loudness.__dict__,
        "cuts": notes,
        "provenance": provenance,
        "words": shifted,
    }


def shift_words(words: list[Word], offset: float, duration: float) -> list[Word]:
    def clamp(time: float) -> float:
        return round(min(duration, max(0.0, time - offset)), 3)

    return [{"text": w["text"], "start": clamp(float(w["start"])), "end": clamp(float(w["end"]))} for w in words]


def slice_words(words: list[Word], raw_words: list[Word], pick: Pick) -> list[Word]:
    if pick.first_word is None and pick.last_word is None:
        return words
    if len(words) != len(raw_words):
        sys.exit(f"error: {pick.line}: caption_joins change word indices; put joins on lines without first_word/last_word")
    return words[pick.first_word or 0 : pick.last_word]


def public_prefix(out: Path, override: str | None) -> str:
    if override is not None:
        return override.strip("/")
    parts = out.resolve().parts
    if "public" in parts:
        return "/".join(parts[len(parts) - parts[::-1].index("public") :])
    return out.as_posix().strip("/")


def processing(args: argparse.Namespace) -> Processing:
    return Processing(highpass=args.highpass, trim=not args.no_trim, true_peak=args.true_peak, max_limiting=args.max_limiting,
                      target_lufs=None if args.no_loudness else args.target_lufs)


def main() -> int:
    args = parse_args()
    picks = Picks.model_validate_json(args.picks.read_text())
    audio.binary("ffmpeg", args.verbose)
    audio.binary("ffprobe", args.verbose)
    args.out.mkdir(parents=True, exist_ok=True)
    prefix = public_prefix(args.out, args.public_prefix)
    settings = processing(args)
    lines = []
    with tempfile.TemporaryDirectory(prefix="vo-build-") as work:
        for pick in picks.lines:
            print(f"{pick.line} <- {pick.take} (tempo {pick.tempo})")
            lines.append(build_line(pick, args, settings, prefix, Path(work)))
    summary = report.loudness_summary(lines, settings.target_lufs, QUIET_DELTA)
    report.write_outputs(lines, summary, args, TS_FIELDS)
    report.print_table(lines, summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
