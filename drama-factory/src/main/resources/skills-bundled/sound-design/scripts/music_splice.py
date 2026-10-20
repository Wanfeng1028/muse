#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["numpy>=2", "scipy>=1.11", "librosa>=0.11", "soundfile>=0.12"]
# ///
"""Music editing: rank splice points, render an edit with equal-power crossfades, export blind-test excerpts."""
import argparse
import json
import secrets
import shutil
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_audio import dsp, media  # noqa: E402

ANALYSIS_RATE = 22050
RENDER_RATE = 48000
HOP = 512
JUDGE_PROMPT = (
    "This is an {seconds:.0f}-second instrumental excerpt. Some excerpts contain an editor's splice (two different parts of a "
    "song joined), others are untouched. Is there a splice? Answer: SPLICE: yes/no | WHERE: m:ss or none | HOW NOTICEABLE 1-10 | WHY (one sentence)."
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rank bar-aligned splice points by chroma similarity, render edits with equal-power crossfades, export blind-test excerpts.",
        epilog=(
            "rank:   uv run music_splice.py rank track.mp3 --beats out/track.beats.json --target-length 45\n"
            "        uv run music_splice.py rank track.mp3 --cut 60.86 --entry-range 140 166\n"
            "        uv run music_splice.py rank track.mp3 --entry 160.8 --cut-range 48 68\n"
            "render: uv run music_splice.py render track.mp3 --segments 0:70.915,172.047:173.75 --out out/music-edit.wav\n"
            "blind:  uv run music_splice.py blind out/music-edit.wav --source track.mp3 --length 8\n"
            "Similarity compares the original continuation after the cut with the music after the entry (and the lead-ins before them)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    rank = commands.add_parser("rank", help="rank splice candidates")
    rank.add_argument("track", type=Path)
    rank.add_argument("--beats", type=Path, help="beats.json from music_analyze.py (else beats are tracked here, phase 0)")
    rank.add_argument("--cut", type=float, help="fixed cut time A; rank entries B")
    rank.add_argument("--entry", type=float, help="fixed entry time B; rank cuts A")
    rank.add_argument("--entry-range", type=float, nargs=2, metavar=("FROM", "TO"))
    rank.add_argument("--cut-range", type=float, nargs=2, metavar=("FROM", "TO"))
    rank.add_argument("--target-length", type=float, help="search cut/entry pairs giving this edited length")
    rank.add_argument("--start", type=float, default=0.0, help="edit starts at this source time")
    rank.add_argument("--end", type=float, help="edit ends at this source time (default: track end)")
    rank.add_argument("--tolerance", type=float, default=0.6, help="target-length tolerance (s)")
    rank.add_argument("--window", type=float, default=5.0, help="seconds compared on each side")
    rank.add_argument("--any-beat", action="store_true", help="allow any beat, not only bar lines")
    rank.add_argument("--top", type=int, default=8)
    render = commands.add_parser("render", help="render an edit")
    render.add_argument("track", type=Path)
    render.add_argument("--segments", required=True, help="source spans 'start:end,start:end,...' (seconds)")
    render.add_argument("--fade-ms", type=float, default=12.0)
    render.add_argument("--curve", choices=("power", "linear"), default="power", help="linear suits joins between near-identical repeats")
    render.add_argument("--beats", type=Path, help="warn when a cut is more than 30 ms off a bar line")
    render.add_argument("--out", type=Path, default=Path("out/music-edit.wav"))
    blind = commands.add_parser("blind", help="edited vs untouched excerpts for a judge")
    blind.add_argument("edit", type=Path, help="rendered edit (its .joins.json is read for the join time)")
    blind.add_argument("--source", type=Path, required=True, help="the untouched track")
    blind.add_argument("--join", type=float, help="join time in the edit (default: first join in .joins.json)")
    blind.add_argument("--length", type=float, default=8.0)
    blind.add_argument("--controls", type=int, default=1, help="untouched excerpts to mix in")
    blind.add_argument("--format", choices=("mp3", "wav"), default="mp3")
    blind.add_argument("--out-dir", type=Path, default=Path("out/review/splice-blind"))
    blind.add_argument("--seed", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def load_grid(track: Path, beats_path: Path | None, samples: np.ndarray, any_beat: bool) -> np.ndarray:
    if beats_path:
        data = json.loads(beats_path.read_text())
        return np.array(data["beats"] if any_beat else data["bars"])
    _, beats = librosa.beat.beat_track(y=samples, sr=ANALYSIS_RATE, units="time")
    print("note: no --beats given; tracked beats here and assumed bar phase 0 (run music_analyze.py for a checked grid)")
    return np.asarray(beats) if any_beat else np.asarray(beats)[::4]


class Similarity:
    def __init__(self, samples: np.ndarray, window: float) -> None:
        self.chroma = librosa.feature.chroma_cqt(y=samples, sr=ANALYSIS_RATE, hop_length=HOP)
        self.samples = samples
        self.span = int(window * ANALYSIS_RATE / HOP)

    def _frame(self, seconds: float) -> int:
        return int(seconds * ANALYSIS_RATE / HOP)

    def _compare(self, a: int, b: int) -> float:
        x, y = self.chroma[:, max(a, 0) : max(a, 0) + self.span], self.chroma[:, max(b, 0) : max(b, 0) + self.span]
        count = min(x.shape[1], y.shape[1])
        if count < 4:
            return float("nan")
        return float(np.nanmean([np.corrcoef(x[:, i], y[:, i])[0, 1] for i in range(count)]))

    def score(self, cut: float, entry: float) -> dict[str, float]:
        after = self._compare(self._frame(cut), self._frame(entry))
        before = self._compare(self._frame(cut) - self.span, self._frame(entry) - self.span)
        level_cut = dsp.rms_db(self.samples[int(cut * ANALYSIS_RATE) : int((cut + 1) * ANALYSIS_RATE)])
        level_entry = dsp.rms_db(self.samples[int(entry * ANALYSIS_RATE) : int((entry + 1) * ANALYSIS_RATE)])
        jump = level_entry - level_cut
        score = np.nan_to_num(after, nan=-1) + 0.5 * np.nan_to_num(before, nan=0) - 0.03 * abs(jump)
        return {"cut": round(cut, 3), "entry": round(entry, 3), "score": round(float(score), 3), "after": round(after, 3), "before": round(before, 3), "level_jump_db": round(jump, 1)}


def candidate_pairs(arguments: argparse.Namespace, grid: np.ndarray, duration: float) -> list[tuple[float, float]]:
    end = arguments.end or duration
    margin = arguments.window
    if arguments.target_length:
        pairs = []
        for cut in grid[(grid > arguments.start + 1) & (grid < end - margin)]:
            wanted = cut + end - arguments.start - arguments.target_length
            pairs += [(float(cut), float(e)) for e in grid if abs(e - wanted) <= arguments.tolerance and e > cut + margin]
        return pairs
    if arguments.cut is not None:
        low, high = arguments.entry_range or (0, duration)
        return [(arguments.cut, float(e)) for e in grid if low <= e <= high and abs(e - arguments.cut) > margin]
    if arguments.entry is not None:
        low, high = arguments.cut_range or (0, duration)
        return [(float(c), arguments.entry) for c in grid if low <= c <= high and abs(c - arguments.entry) > margin]
    raise SystemExit("rank needs --cut, --entry or --target-length")


def run_rank(arguments: argparse.Namespace) -> None:
    samples = media.decode(arguments.track, ANALYSIS_RATE, 1)[:, 0]
    duration = len(samples) / ANALYSIS_RATE
    grid = load_grid(arguments.track, arguments.beats, samples, arguments.any_beat)
    pairs = candidate_pairs(arguments, grid, duration)
    if not pairs:
        raise SystemExit("no candidates on the grid; widen the ranges or --tolerance, or use --any-beat")
    similarity = Similarity(samples, arguments.window)
    end = arguments.end or duration
    scored = [similarity.score(cut, entry) for cut, entry in pairs]
    scored.sort(key=lambda row: -row["score"])
    print(f"{len(scored)} candidates; score = after + 0.5 before - 0.03 |level jump|; after = continuation match, before = lead-in match (1.0 = identical)")
    for row in scored[: arguments.top]:
        length = row["cut"] - arguments.start + end - row["entry"]
        print(f"  cut {row['cut']:8.3f} -> entry {row['entry']:8.3f}   score {row['score']:.2f}  after {row['after']:.2f}  before {row['before']:.2f}  level {row['level_jump_db']:+.1f} dB  edit length {length:.2f}s")
    best = scored[0]
    print(f"render: --segments {arguments.start:g}:{best['cut']:g},{best['entry']:g}:{end:g}")


def parse_segments(text: str) -> list[tuple[float, float]]:
    segments = []
    for part in text.split(","):
        start, end = (float(value) for value in part.split(":"))
        if end <= start:
            raise SystemExit(f"segment {part}: end must be after start")
        segments.append((start, end))
    return segments


def run_render(arguments: argparse.Namespace) -> None:
    segments = parse_segments(arguments.segments)
    source = media.decode(arguments.track, RENDER_RATE, 2)
    edited, joins = dsp.splice_segments(source, segments, RENDER_RATE, arguments.fade_ms / 1000, arguments.curve)
    if arguments.beats:
        bars = np.array(json.loads(arguments.beats.read_text())["bars"])
        for edge in [s[1] for s in segments[:-1]] + [s[0] for s in segments[1:]]:
            if np.min(np.abs(bars - edge)) > 0.03:
                print(f"warning: cut at {edge:.3f}s is {np.min(np.abs(bars - edge)) * 1000:.0f} ms from the nearest bar line")
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(arguments.out, edited, RENDER_RATE, subtype="FLOAT")
    joins_path = arguments.out.with_suffix(".joins.json")
    joins_path.write_text(json.dumps({"source": str(arguments.track), "segments": segments, "joins": [round(j, 4) for j in joins], "fade_ms": arguments.fade_ms}, indent=2) + "\n")
    print(f"edit {len(edited) / RENDER_RATE:.3f}s, joins at {', '.join(f'{j:.3f}s' for j in joins) or 'none'}")
    print(arguments.out)
    print(joins_path)


def excerpt(path: Path, start: float, length: float, destination: Path) -> None:
    media.run_ffmpeg(["-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(path), "-ar", "44100", *(["-b:a", "192k"] if destination.suffix == ".mp3" else []), str(destination)])


def run_blind(arguments: argparse.Namespace) -> None:
    rng = np.random.default_rng(arguments.seed)
    joins_info = json.loads(arguments.edit.with_suffix(".joins.json").read_text()) if arguments.edit.with_suffix(".joins.json").exists() else {}
    join = arguments.join if arguments.join is not None else (joins_info.get("joins") or [None])[0]
    if join is None:
        raise SystemExit("no join time: pass --join or render the edit with this script first")
    edit_seconds = soundfile.info(arguments.edit).duration
    source_seconds = len(media.decode(arguments.source, 8000, 1)) / 8000
    offset = float(rng.uniform(0.3, 0.7)) * arguments.length
    edit_start = min(max(0.0, join - offset), max(0.0, edit_seconds - arguments.length))
    cuts = [edge for segment in joins_info.get("segments", []) for edge in segment]
    if arguments.out_dir.exists():
        shutil.rmtree(arguments.out_dir)
    arguments.out_dir.mkdir(parents=True)
    entries = [("edited", arguments.edit, edit_start, round(join - edit_start, 3))]
    for _ in range(arguments.controls):
        for _attempt in range(200):
            start = float(rng.uniform(0, max(0.0, source_seconds - arguments.length)))
            if all(not (start - 0.5 < edge < start + arguments.length + 0.5) for edge in cuts[1:-1]):
                break
        entries.append(("control", arguments.source, start, None))
    rng.shuffle(entries)
    key = {"prompt": JUDGE_PROMPT.format(seconds=arguments.length), "excerpts": {}}
    for kind, path, start, join_in_excerpt in entries:
        name = f"excerpt-{secrets.token_hex(3)}.{arguments.format}"
        excerpt(path, start, arguments.length, arguments.out_dir / name)
        key["excerpts"][name] = {"kind": kind, "from": str(path), "start": round(start, 3), "join_at": join_in_excerpt}
        print(arguments.out_dir / name)
    key_path = arguments.out_dir.parent / f"{arguments.out_dir.name}.key.json"
    key_path.write_text(json.dumps(key, indent=2) + "\n")
    print(f"{key_path}  (private: do not show the judge)")
    print("judge prompt: " + key["prompt"])


def main() -> None:
    arguments = parse_arguments()
    media.set_verbose(arguments.verbose)
    {"rank": run_rank, "render": run_render, "blind": run_blind}[arguments.command](arguments)


if __name__ == "__main__":
    main()
