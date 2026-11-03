#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2", "scipy>=1.11", "soundfile>=0.12", "pyloudnorm>=0.1.1", "pydantic>=2.6"]
# ///
"""Offline film mixer: cues.json -> one mastered WAV (-14 LUFS / -1 dBTP) plus stems and a loudness report."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile
from pydantic import ValidationError
from scipy.signal import butter, lfilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foley  # noqa: E402
from lib_audio import audibility, dsp, limiter, media  # noqa: E402
from lib_audio.cues_model import Clip, Cues, Music  # noqa: E402

RATE = foley.RATE
SCHEMA_SUMMARY = """cues.json (full spec: scripts/cues.schema.md; keys camelCase or snake_case):
  duration   seconds, required; the mix is exactly this long
  key        music key for pitched foley ("F", "A minor"); --key overrides
  music      {file, segments:[{sourceStart,sourceEnd},...] | edit:{a:{..},b:{..}}, at, gainDb, fadeIn, tempo, beats}
  vo         [{file, at, gainDb, sourceStart, sourceEnd, align:start|peak, id}]   normalized as one stem to --vo-lufs
  product    [{...same as vo}]  product/diegetic voice or sound (alias: cards, diegetic), stem to --product-lufs
  sfx        [{kind|file, at, gain, gainDb, note, length, variant, align:peak|start, role:event|texture}]  peak lands on `at`
Relative files resolve against --root, then the cwd, then the cues file's folder."""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mix music edit, VO, product clips and SFX from cues.json: band-split ducking, two-pass loudnorm, stems, LUFS report.",
        epilog=SCHEMA_SUMMARY + "\n\nExample: uv run mix.py out/cues.json --root public --out public/audio/mix.wav --json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add = parser.add_argument
    add("cues", type=Path, nargs="?", help="cues.json")
    add("--root", type=Path, default=None, help="base folder for relative files (default: ./public if it exists)")
    add("--out", type=Path, default=Path("out/mix.wav"))
    add("--stems", type=Path, default=Path("out/stems"), help="folder for vo/product/sfx/music stems and mix-raw.wav")
    add("--key", default=None, help="music key for pitched foley (default: cues key, else C)")
    add("--seed", type=int, default=7, help="foley noise seed")
    add("--vo-lufs", type=float, default=-16.0)
    add("--product-lufs", type=float, default=-17.0)
    add("--music-lufs", type=float, default=-19.0, help="bed level before ducking (what plays in the gaps)")
    add("--sfx-peak-db", type=float, default=-10.5, help="each SFX peak-normalized to this, times its cue gain")
    add("--sfx-median-db", type=float, default=-12.0, help="fail when event SFX sit, at the median, further than this under voice+music")
    add("--sfx-cue-db", type=float, default=-20.0, help="warn for each event SFX further than this under voice+music")
    add("--duck-db", type=float, default=6.0, help="bed reduction under speech, whole band")
    add("--duck-high-db", type=float, default=3.0, help="extra reduction above --duck-split-hz (clears the speech band)")
    add("--duck-split-hz", type=float, default=3500.0)
    add("--attack", type=float, default=0.08, help="duck attack seconds")
    add("--release", type=float, default=0.6, help="duck release seconds (slow on purpose)")
    add("--duck-lookahead", type=float, default=0.05, help="start ducking this many seconds before speech")
    add("--duck-floor-db", type=float, default=-40.0, help="speech envelope (dBFS) where ducking starts")
    add("--duck-knee-db", type=float, default=12.0, help="dB above the floor where ducking is full")
    add("--no-duck-product", action="store_true", help="key the duck on VO only, not product clips")
    add("--splice-ms", type=float, default=12.0, help="crossfade at each music join")
    add("--splice-curve", choices=("power", "linear"), default="power", help="equal-power (default) or equal-gain for near-identical repeats")
    add("--lufs", type=float, default=-14.0, help="integrated loudness target")
    add("--true-peak", type=float, default=-1.0, help="true peak ceiling dBTP")
    add("--lra", type=float, default=11.0)
    add("--tail-fade", type=float, default=0.9, help="seconds of curved fade at the end (0 = off)")
    add("--tail-curve", type=float, default=1.3)
    add("--no-limiter", action="store_true", help="skip the true-peak limiter that keeps loudnorm in linear mode")
    add("--limiter-margin", type=float, default=0.3, help="dB of headroom under the ceiling the limiter leaves")
    add("--bits", type=int, choices=(16, 24), default=16)
    add("--json", action="store_true", help="write <out>.report.json")
    add("--check", action="store_true", help="validate cues and resolve files, then exit")
    add("--print-schema", action="store_true", help="print the JSON Schema of cues.json and exit")
    add("--verbose", action="store_true")
    return parser.parse_args()


def resolver(root: Path | None, cues_path: Path):
    roots = [r for r in (root if root else Path("public"), Path.cwd(), cues_path.resolve().parent) if r]

    def resolve(text: str) -> Path:
        path = Path(text)
        if path.is_absolute():
            return path
        for base in roots:
            if (base / path).exists():
                return base / path
        raise SystemExit(f"file not found: {text} (looked in {', '.join(str(r) for r in roots)})")

    return resolve


def clip_audio(clip: Clip, path: Path) -> np.ndarray:
    audio = media.decode(path, RATE, 2)
    start = int(clip.source_start * RATE)
    end = int(clip.source_end * RATE) if clip.source_end is not None else len(audio)
    return audio[start:end]


def normalize(meter: pyloudnorm.Meter, signal: np.ndarray, target: float) -> float:
    measured = float(meter.integrated_loudness(signal)) if np.any(signal) else float("-inf")
    if np.isfinite(measured):
        signal *= dsp.db_to_gain(target - measured)
    return measured


def voice_stem(clips: list[Clip], length: int, resolve, label: str, warnings: list[str]) -> np.ndarray:
    stem = np.zeros((length, 2), dtype=np.float32)
    spans: list[tuple[float, float, str]] = []
    for index, clip in enumerate(clips):
        audio = clip_audio(clip, resolve(clip.file))
        start = int(round(clip.at * RATE)) - (dsp.peak_index(audio) if clip.align == "peak" else 0)
        placed_start, placed_end = dsp.place(stem, audio, start, dsp.db_to_gain(clip.gain_db))
        if start + len(audio) > length:
            warnings.append(f"{label} {clip.id or clip.file} runs past the film end and is cut at {length / RATE:.2f}s")
        spans.append((start / RATE, (start + len(audio)) / RATE, clip.id or Path(clip.file).stem or str(index)))
    spans.sort()
    for (_, end_a, name_a), (start_b, _, name_b) in zip(spans, spans[1:]):
        if start_b < end_a:
            warnings.append(f"{label} overlap: {name_a} ends {end_a:.2f}s after {name_b} starts {start_b:.2f}s")
    return stem


def sfx_stem(cues: Cues, length: int, resolve, peak_db: float, key: str, seed: int) -> np.ndarray:
    stem = np.zeros((length, 2), dtype=np.float32)
    for cue in cues.sfx:
        if cue.kind:
            audio = foley.render(cue.kind, cue.note, key, cue.length, cue.variant, seed)
        else:
            audio = media.decode(resolve(cue.file), RATE, 2)
        audio = audio / (np.abs(audio).max() or 1.0)
        start = int(round(cue.at * RATE)) - (dsp.peak_index(audio) if cue.align == "peak" else 0)
        dsp.place(stem, audio, start, dsp.db_to_gain(peak_db + cue.gain_db) * cue.gain)
    return stem


def check_bars(music: Music, resolve, warnings: list[str]) -> None:
    if not music.beats:
        return
    bars = np.array(json.loads(resolve(music.beats).read_text()).get("bars", []))
    if not len(bars):
        return
    for index, segment in enumerate(music.segments or []):
        edges = ([segment.source_start] if index > 0 else []) + ([segment.source_end] if index < len(music.segments) - 1 else [])
        for edge in edges:
            distance = float(np.min(np.abs(bars - edge)))
            if distance > 0.03:
                warnings.append(f"music cut at {edge:.3f}s is {distance * 1000:.0f} ms from the nearest bar line")


def music_stem(music: Music, length: int, resolve, splice_ms: float, curve: str, warnings: list[str]) -> np.ndarray:
    filters = f"atempo={music.tempo}" if music.tempo != 1.0 else None
    source = media.decode(resolve(music.file), RATE, 2, filters)
    segments = [(s.source_start / music.tempo, s.source_end / music.tempo) for s in music.segments or []]
    edited, _ = dsp.splice_segments(source, segments, RATE, splice_ms / 1000, curve) if segments else (source, [])
    dsp.apply_fade_in(edited, RATE, music.fade_in)
    stem = np.zeros((length, 2), dtype=np.float32)
    dsp.place(stem, edited, int(round(music.at * RATE)))
    music_end = music.at + len(edited) / RATE
    if music_end < length / RATE - 0.05:
        warnings.append(f"music ends at {music_end:.2f}s, before the film end {length / RATE:.2f}s")
    return stem


def duck(music: np.ndarray, speech: np.ndarray, arguments: argparse.Namespace) -> tuple[np.ndarray, np.ndarray]:
    level = dsp.envelope_follower(speech, RATE, arguments.attack, arguments.release)
    shift = int(arguments.duck_lookahead * RATE)
    if shift > 0:
        level = np.concatenate([level[shift:], np.full(shift, level[-1], dtype=np.float32)])
    level_db = 20 * np.log10(np.maximum(level, 1e-6))
    amount = np.clip((level_db - arguments.duck_floor_db) / arguments.duck_knee_db, 0, 1)[:, None]
    low = lfilter(*butter(2, arguments.duck_split_hz / (RATE / 2)), music, axis=0).astype(np.float32)
    high = music - low
    whole = dsp.db_to_gain(-arguments.duck_db) ** amount
    extra = dsp.db_to_gain(-arguments.duck_db - arguments.duck_high_db) ** amount
    return (low * whole + high * extra).astype(np.float32), amount[:, 0]


def pre_limit(mix: np.ndarray, meter: pyloudnorm.Meter, arguments: argparse.Namespace) -> float:
    """Limit peaks so the loudnorm gain to target cannot push true peak over the ceiling."""
    deepest = 0.0
    for _ in range(4):
        loudness = float(meter.integrated_loudness(mix))
        if not np.isfinite(loudness):
            return deepest
        reduction = limiter.limit(mix, RATE, arguments.true_peak - (arguments.lufs - loudness) - arguments.limiter_margin)
        deepest = max(deepest, reduction)
        if reduction < 0.05:
            break
    return deepest


def measured_lufs(meter: pyloudnorm.Meter, signal: np.ndarray) -> float | None:
    if not np.any(signal):
        return None
    value = float(meter.integrated_loudness(signal))
    return round(value, 1) if np.isfinite(value) else None


def main() -> None:
    arguments = parse_arguments()
    if arguments.print_schema:
        print(json.dumps(Cues.model_json_schema(by_alias=True), indent=2))
        return
    if not arguments.cues:
        sys.exit("give a cues.json path (see --help)")
    media.set_verbose(arguments.verbose)
    try:
        cues = Cues.model_validate_json(arguments.cues.read_text())
    except ValidationError as error:
        sys.exit(f"invalid {arguments.cues}:\n{error}")
    resolve = resolver(arguments.root, arguments.cues)
    key = arguments.key or cues.key or "C"
    unknown_kinds = sorted({cue.kind for cue in cues.sfx if cue.kind and cue.kind not in foley.KINDS})
    if unknown_kinds:
        sys.exit(f"unknown sfx kinds {unknown_kinds}; foley kinds: {', '.join(foley.KINDS)}")
    try:
        foley.parse_key(key)
    except ValueError as error:
        sys.exit(str(error))
    files = [c.file for c in cues.vo + cues.product] + [s.file for s in cues.sfx if s.file] + ([cues.music.file] if cues.music else [])
    paths = [resolve(f) for f in files]
    if arguments.check:
        print(f"OK: {len(cues.vo)} VO, {len(cues.product)} product, {len(cues.sfx)} sfx, {len(set(paths))} files resolved, key {key}")
        return

    length = int(round(cues.duration * RATE))
    meter = pyloudnorm.Meter(RATE)
    warnings: list[str] = []
    vo = voice_stem(cues.vo, length, resolve, "VO", warnings)
    vo_in = normalize(meter, vo, arguments.vo_lufs)
    product = voice_stem(cues.product, length, resolve, "product", warnings)
    normalize(meter, product, arguments.product_lufs)
    sfx = sfx_stem(cues, length, resolve, arguments.sfx_peak_db, key, arguments.seed)
    music = np.zeros((length, 2), dtype=np.float32)
    if cues.music:
        check_bars(cues.music, resolve, warnings)
        music = music_stem(cues.music, length, resolve, arguments.splice_ms, arguments.splice_curve, warnings)
        normalize(meter, music, arguments.music_lufs + cues.music.gain_db)
    speech = vo if arguments.no_duck_product else vo + product
    ducked, amount = duck(music, speech, arguments)

    mix = vo + product + sfx + ducked
    dsp.apply_tail_fade(mix, RATE, arguments.tail_fade, arguments.tail_curve)
    limited_db = 0.0 if arguments.no_limiter else pre_limit(mix, meter, arguments)
    arguments.stems.mkdir(parents=True, exist_ok=True)
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    written = []
    for name, stem in (("vo", vo), ("product", product), ("sfx", sfx), ("music", ducked), ("mix-raw", mix)):
        path = arguments.stems / f"{name}.wav"
        soundfile.write(path, stem, RATE, subtype="FLOAT")
        written.append(path)
    target = media.LoudnessTarget(arguments.lufs, arguments.true_peak, arguments.lra)
    applied = media.loudnorm_two_pass(arguments.stems / "mix-raw.wav", arguments.out, target, RATE, f"pcm_s{arguments.bits}le")
    final = media.measure(arguments.out, target)
    under_speech = amount > 0.5
    heard = audibility.assess(audibility.cue_levels(cues.sfx, sfx, vo + product + ducked, RATE), arguments.sfx_median_db, arguments.sfx_cue_db)
    duck_depth = dsp.rms_db(ducked[under_speech]) - dsp.rms_db(music[under_speech]) if under_speech.any() and np.any(music) else None
    report = {
        "out": str(arguments.out),
        "duration": round(length / RATE, 3),
        "integrated_lufs": float(final["input_i"]),
        "true_peak_dbtp": float(final["input_tp"]),
        "lra": float(final["input_lra"]),
        "normalization": applied.get("normalization_type"),
        "master_gain_db": round(float(final["input_i"]) - float(applied["first_pass_input_i"]), 2),
        "stems_lufs": {name: measured_lufs(meter, stem) for name, stem in (("vo", vo), ("product", product), ("sfx", sfx), ("music", ducked))},
        "vo_source_lufs": round(vo_in, 1) if np.isfinite(vo_in) else None,
        "average_duck_under_speech_db": round(duck_depth, 1) if duck_depth is not None else None,
        "limiter_max_reduction_db": round(limited_db, 2),
        "key": key,
        "sfx_audibility": heard.model_dump(),
        "warnings": warnings,
    }
    loudness_passed = abs(report["integrated_lufs"] - arguments.lufs) <= 0.5 and report["true_peak_dbtp"] <= arguments.true_peak + 0.05
    for path in written + [arguments.out]:
        print(path)
    print(f"mix {report['duration']}s: {report['integrated_lufs']} LUFS, TP {report['true_peak_dbtp']} dBTP, LRA {report['lra']} ({report['normalization']})")
    print("stems LUFS: " + ", ".join(f"{k} {v}" for k, v in report["stems_lufs"].items()) + f"; master gain {report['master_gain_db']} dB on the stems")
    print(f"average bed duck under speech: {report['average_duck_under_speech_db']} dB; limiter max reduction {report['limiter_max_reduction_db']} dB")
    for warning in warnings:
        print(f"warning: {warning}")
    for line in audibility.describe(heard, arguments.sfx_cue_db):
        print(line)
    if report["normalization"] == "dynamic":
        print("warning: loudnorm fell back to dynamic mode (it compresses); keep the limiter on, or lower --sfx-peak-db and hot cues")
    if arguments.json:
        report_path = arguments.out.with_suffix(".report.json")
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(report_path)
    failures = [] if loudness_passed else [f"FAIL: target {arguments.lufs} LUFS / {arguments.true_peak} dBTP"]
    if not heard.passed:
        failures.append(f"FAIL: event SFX median {heard.event_median_db} dB under voice+music (floor {arguments.sfx_median_db}); raise cue gains")
    print("\n".join(failures) or "PASS")
    sys.exit(2 if failures else 0)


if __name__ == "__main__":
    main()
