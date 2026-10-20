#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Ask an audio/video-capable model (OpenRouter, default a Gemini Pro id) to judge media, with strict one-line formats.

Modes
  vo-take       per take: TRANSCRIPT | ERRORS | ACCENT | DELIVERY 1-10 + why, against the intended text
  pairwise      two takes: WINNER: A or B | why (--runs > 1 alternates the order to cancel position bias)
  blind-splice  edited excerpt + untouched control, judged separately, shuffled, file names hidden, --runs N, tallied
  music-fit     one-line scoring card per track against a --brief
  chunks        a track cut into chunks: instruments | energy | vocals | events | VO-friendly
  restate       muted video, cold viewer: state the message in one sentence
  ask           free prompt over any files (one request)

Limits (read before trusting a verdict)
  - Video judges sample about 1 fps. They miss easing, 1-frame pops, flashes and fast moves, and they hallucinate
    details (easing, emojis, gradients that are not there). Use them for gist, comprehension, pacing feel and
    transcription only. Verify every specific motion or frame claim with frame strips or stills before acting.
  - Audio judges need a blind setup: never reveal which clip is edited, always include an untouched control from the
    same source, and repeat runs. A single answer is noise; a tally against the control is evidence.
  - A model's "sounds great" or "looks great" is never a pass. A measured envelope or a frame strip beats any opinion.

Examples
  media_judge.py vo-take out/vo/takes/*.mp3 --brief "female, warm, playful TV ad" --accent "Colombian Spanish"
  media_judge.py pairwise out/vo/takes/l03a.mp3 out/vo/takes/l03b.mp3 --runs 2
  media_judge.py blind-splice out/review/edited.wav out/review/control.wav --runs 10
  media_judge.py music-fit music/*.mp3 --brief "60 s launch film for parents, warm, female VO on top"
  media_judge.py chunks music/track.mp3 --chunk 8 --offset 0.42
  media_judge.py restate out/final/film-16x9.mp4

Output: <stem>.judge.txt (vo-take) or <stem>.<mode>.judge.txt next to the first input (or in --out-dir), plus a
summary on stdout and the total cost when OpenRouter reports it. Key: OPENROUTER_API_KEY (env or --env-file).
"""
import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _media_judge_prompts as prompts
from _media_judge_core import (
    Answer,
    Request,
    ask,
    audio_part,
    describe_part,
    is_video,
    load_env_file,
    probe_duration,
    require_key,
    save_json,
    text_part,
    video_part,
)

DEFAULT_MODEL = "~google/gemini-pro-latest"


def common_options() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenRouter model id (default {DEFAULT_MODEL})")
    parent.add_argument("--concurrency", type=int, default=2, help="requests in flight (default 2)")
    parent.add_argument("--out-dir", type=Path, help="where to write judge files (default: next to the input)")
    parent.add_argument("--env-file", type=Path, help="KEY=VALUE file to read OPENROUTER_API_KEY from")
    parent.add_argument("--json", action="store_true", help="also write the raw answers as JSON")
    parent.add_argument("--dry-run", action="store_true", help="package media and print the requests; send nothing")
    return parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0], epilog=__doc__.split("\n\n", 1)[1],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_subparsers(dest="mode", required=True)
    parent = common_options()
    take = modes.add_parser("vo-take", parents=[parent], help="judge VO takes against their intended text")
    take.add_argument("files", nargs="+", type=Path)
    take.add_argument("--text", help="intended text (default: 'text' in each take's <stem>.json sidecar)")
    take.add_argument("--brief", default=prompts.VO_BRIEF, help="voice direction, e.g. 'female, warm, Colombian TV ad'")
    take.add_argument("--accent", help="expected accent, e.g. 'Colombian Spanish'")
    pair = modes.add_parser("pairwise", parents=[parent], help="A/B two takes of the same line")
    pair.add_argument("files", nargs=2, type=Path)
    pair.add_argument("--brief", default=prompts.VO_BRIEF)
    pair.add_argument("--runs", type=int, default=1, help="repeats; even runs swap the order (default 1)")
    splice = modes.add_parser("blind-splice", parents=[parent], help="blind test: edited excerpt vs untouched control")
    splice.add_argument("files", nargs=2, type=Path, metavar="EDITED CONTROL")
    splice.add_argument("--runs", type=int, default=5, help="repeats per clip (default 5)")
    splice.add_argument("--prompt", help="custom neutral question; answers must contain 'SPLICE: yes/no' or 'SCORE: n'")
    splice.add_argument("--margin", type=float, default=0.3, help="edited minus control yes-rate that fails (default 0.3)")
    splice.add_argument("--seed", type=int, help="shuffle seed")
    music = modes.add_parser("music-fit", parents=[parent], help="score tracks against a film brief")
    music.add_argument("files", nargs="+", type=Path)
    music.add_argument("--brief", required=True, help="the film: product, audience, tone, VO on top or not")
    chunks = modes.add_parser("chunks", parents=[parent], help="describe a track chunk by chunk")
    chunks.add_argument("files", nargs="+", type=Path)
    chunks.add_argument("--chunk", type=float, default=8.0, help="chunk length in seconds (default 8)")
    chunks.add_argument("--offset", type=float, default=0.0, help="first chunk boundary, e.g. the first downbeat (default 0)")
    chunks.add_argument("--vo-brief", default="a soft voiceover", help="the VO the music must sit under")
    restate = modes.add_parser("restate", parents=[parent], help="muted cold-viewer comprehension test")
    restate.add_argument("files", nargs="+", type=Path)
    restate.add_argument("--height", type=int, default=480, help="re-encode height for upload (default 480)")
    free = modes.add_parser("ask", parents=[parent], help="free prompt over any files")
    free.add_argument("files", nargs="+", type=Path)
    free.add_argument("--prompt", required=True)
    free.add_argument("--blind", action="store_true", help="label files Clip 1, Clip 2 instead of their names")
    free.add_argument("--height", type=int, default=480)
    free.add_argument("--with-audio", action="store_true", help="keep the soundtrack of video files")
    return parser.parse_args()


def intended_text(path: Path, override: str | None) -> str:
    if override:
        return override
    sidecar = path.with_suffix(".json")
    if not sidecar.is_file():
        sys.exit(f"error: no --text and no sidecar {sidecar}")
    return json.loads(sidecar.read_text())["text"]


def build_requests(args: argparse.Namespace) -> list[Request]:
    if args.mode == "vo-take":
        return [Request(path.stem, [text_part(prompts.vo_take(intended_text(path, args.text), args.brief, args.accent)), audio_part(path)], {"path": path})
                for path in args.files]
    if args.mode == "pairwise":
        first, second = args.files
        orders = [(first, second) if run % 2 == 0 else (second, first) for run in range(args.runs)]
        return [Request(f"run{run + 1}", [text_part(prompts.pairwise(args.brief)), audio_part(a), audio_part(b)], {"a": a, "b": b})
                for run, (a, b) in enumerate(orders)]
    if args.mode == "blind-splice":
        return blind_requests(args)
    if args.mode == "music-fit":
        return [Request(path.stem, [text_part(prompts.music_fit(args.brief)), audio_part(path)], {"path": path}) for path in args.files]
    if args.mode == "chunks":
        return [request for path in args.files for request in chunk_requests(path, args)]
    if args.mode == "restate":
        return [Request(path.stem, [text_part(prompts.RESTATE), video_part(path, args.height, True)], {"path": path}) for path in args.files]
    return [free_request(args)]


def blind_requests(args: argparse.Namespace) -> list[Request]:
    edited, control = args.files
    lengths = {path: probe_duration(path) for path in args.files}
    if abs(lengths[edited] - lengths[control]) > 0.5:
        print(f"WARN: clip lengths differ ({lengths[edited]:.1f}s vs {lengths[control]:.1f}s); length is a tell, match them")
    requests = [
        Request(f"{role}-{run + 1}", [text_part(args.prompt or prompts.blind_splice(lengths[path])), audio_part(path)], {"role": role, "path": path})
        for run in range(args.runs) for role, path in (("edited", edited), ("control", control))
    ]
    random.Random(args.seed).shuffle(requests)
    return requests


def chunk_requests(path: Path, args: argparse.Namespace) -> list[Request]:
    total = probe_duration(path)
    starts = ([0.0] if args.offset > 0 else []) + [args.offset + index * args.chunk for index in range(int(total / args.chunk) + 2)]
    starts = [start for start in starts if start < total - 1]
    requests = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else total
        part = audio_part(path, start, end - start)
        requests.append(Request(f"{path.stem}@{start:.2f}", [text_part(prompts.chunk(args.vo_brief)), part], {"path": path, "start": start}))
    return requests


def free_request(args: argparse.Namespace) -> Request:
    parts = [text_part(args.prompt)]
    for index, path in enumerate(args.files):
        parts.append(text_part(f"Clip {index + 1}:" if args.blind else f"File: {path.name}"))
        parts.append(video_part(path, args.height, not args.with_audio) if is_video(path) else audio_part(path))
    return Request(args.files[0].stem, parts, {"path": args.files[0]})


def print_dry_run(requests: list[Request], model: str) -> None:
    for request in requests:
        print(f"--- request {request.key} -> {model}")
        for part in request.parts:
            print(f"  {describe_part(part)}")
    print(f"dry run: {len(requests)} requests, nothing sent")


def run_requests(requests: list[Request], args: argparse.Namespace) -> list[Answer]:
    load_env_file(args.env_file)
    key = require_key("OPENROUTER_API_KEY")
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        return list(pool.map(lambda request: ask(request, args.model, key), requests))


def target_path(args: argparse.Namespace, path: Path, suffix: str) -> Path:
    return (args.out_dir or path.parent) / f"{path.stem}{suffix}"


def main() -> int:
    args = parse_args()
    missing = [str(path) for path in args.files if not path.is_file()]
    if missing:
        sys.exit(f"error: not found: {', '.join(missing)}")
    requests = build_requests(args)
    if args.dry_run:
        print_dry_run(requests, args.model)
        return 0
    answers = run_requests(requests, args)
    for answer in answers:
        if answer.error:
            print(f"FAIL {answer.request.key}: {answer.error}")
    status = prompts.report(args, answers, target_path)
    if args.json:
        save_json(target_path(args, args.files[0], f".{args.mode}.judge.json"),
                  [{"key": a.request.key, "answer": a.text, "error": a.error, "cost": a.cost, "model": a.model} for a in answers])
    cost = sum(answer.cost for answer in answers)
    models = sorted({answer.model for answer in answers if answer.model})
    print(f"[model {', '.join(models) or args.model}  cost {cost:.4f} USD]" if cost else f"[model {', '.join(models) or args.model}]")
    return 1 if any(answer.error for answer in answers) else status


if __name__ == "__main__":
    sys.exit(main())
