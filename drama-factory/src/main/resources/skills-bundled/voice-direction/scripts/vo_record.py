#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "pydantic>=2", "numpy>=2"]
# ///
"""Record voiceover lines with ElevenLabs text-to-speech, N takes per line, with character alignment and provenance.

Script JSON (a list, one object per line, in film order):
  [{"id": "l01", "text": "[softly] First line...", "previous": null, "next": null, "forms": null}, ...]
  - text: what to say. Inline delivery tags like [softly] [warmly] are directions on eleven_v3/v4, never spoken.
  - previous / next: optional continuity context. When omitted, the neighbouring lines' text is sent with tags stripped,
    wrapped by --context-before/--context-after (an unspoken framing sentence). "" sends no context on that side.
  - forms: optional retake ladder, e.g. ["sol.", "«sol».", "«Sol»."]; with --until-pass each form gets 2 takes
    (--per-form) until a take passes the voice_qa.py gates. Without --until-pass only the first form is recorded.

Each take uses /with-timestamps and writes <out>/<prefix><id><take>.mp3 (.wav for pcm_* formats), <same>.json
({"text", "model", "alignment"}) for vo_build.py, and <same>.meta.json (voice, model, settings, seed, language,
context, request-id, character-cost, ISO date, text form, and the QA verdict with --until-pass). Takes on disk are
skipped; delete a take to redo it. Every request carries a seed (random unless --seed) so a near miss can be re-rolled.

Before sending, a lint pass warns on unbalanced or empty brackets, (parentheses) or {braces} as tags, more than 3 tags,
a tag with nothing after it, digits, % $ @ /, URLs, all-caps acronyms, SSML on v3/v4, [tags] on models that speak
them, and text that reads as another language than --language. --strict turns warnings into errors.
Rate limit: at most 2 requests in flight; 429/5xx retried with backoff (4 tries). Key: ELEVENLABS_API_KEY or --env-file.
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import TypeAdapter

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _voice_eleven as eleven  # noqa: E402
from _vo_record_ladder import Session, run_ladder  # noqa: E402
from _vo_record_lint import lint_text  # noqa: E402
from _vo_record_take import (  # noqa: E402
    Attempt,
    ScriptLine,
    audio_suffix,
    existing_audio,
    meta_for,
    plan_line,
    read_meta,
    record,
    take_slots,
)
from _vo_record_voice import Direction, resolve  # noqa: E402

EXAMPLE = """examples:
  vo_record.py script.json --voice <voice_id> --prefix sofia- --takes 2 --language es --only l03 l07
  vo_record.py script.json --voice voice.json --hero l03 l11 --dry-run
  vo_record.py cards.json --voice voice.json --takes 1 --until-pass --qa-stt scribe --env-file .env.local"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ElevenLabs TTS from a script JSON: N takes per line with alignment + provenance, lint, retake ladder.",
        epilog=__doc__.split("\n\n", 1)[1] + "\n" + EXAMPLE, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add = parser.add_argument
    add("script", type=Path, help='script JSON: [{"id", "text", "previous"?, "next"?, "forms"?}]')
    add("--voice", required=True, help="ElevenLabs voice id, or a project voice file (voice.json; see assets/voice.example.json)")
    add("--model", help="model id (default eleven_v4, or the voice file's)")
    add("--language", help="ISO 639-1 language_code, e.g. es (required unless the voice file has one or --no-language)")
    add("--no-language", action="store_true", help="send no language_code")
    add("--takes", type=int, default=2, help="takes per line (default 2); with --until-pass: passing takes wanted")
    add("--hero", nargs="+", default=[], help="hero line ids (the emotional peak, the CTA) that get --hero-takes")
    add("--hero-takes", type=int, default=3, help="takes for --hero lines (default 3)")
    add("--out", type=Path, default=Path("out/vo/takes"), help="take folder (default out/vo/takes)")
    add("--prefix", default="", help="file name prefix, e.g. the voice name 'sofia-'")
    add("--only", nargs="+", default=[], help="record only these line ids")
    add("--stability", type=float, help="voice stability 0-1 (default 0.5)")
    add("--similarity", type=float, help="similarity boost 0-1 (default 0.75)")
    add("--style", type=float, help="style 0-1 (v2/v3 only; dropped with a warning on eleven_v4)")
    add("--speed", type=float, help="speed (v2/v3/Flash only; dropped on eleven_v4: fix pace with vo_build.py tempo)")
    add("--speaker-boost", action="store_true", default=None, help="use_speaker_boost (v2/v3; dropped on eleven_v4)")
    add("--seed", type=int, help="seed for take a; later takes use seed+1, seed+2 (default: a random seed per take)")
    add("--context-before", help="unspoken framing sentence prepended to previous_text for every line")
    add("--context-after", help="unspoken framing sentence appended to next_text for every line")
    add("--context-file", type=Path, help='JSON {"before", "after"} or text "before\\n---\\nafter"')
    add("--dictionary", action="append", metavar="ID[:VERSION]", help="pronunciation dictionary (repeat, max 3)")
    add("--normalization", choices=["auto", "on", "off"], help="apply_text_normalization (default: API's auto)")
    add("--stitch", action="store_true", help="chain previous_request_ids (long-form chunks only; sequential; not eleven_v3)")
    add("--output-format", help="output_format (default mp3_44100_128; pcm_44100 avoids a double MP3 encode, saved as .wav)")
    add("--until-pass", action="store_true", help="check each take with voice_qa gates and retake down the forms ladder")
    add("--per-form", type=int, default=2, help="takes per ladder form with --until-pass (default 2)")
    add("--retakes", type=int, default=2, help="extra takes for single-form lines with --until-pass (default 2)")
    add("--qa-stt", choices=["none", "scribe"], default="none", help="also run the Scribe STT check in --until-pass (paid)")
    add("--no-lint", action="store_true", help="skip the script lint")
    add("--strict", action="store_true", help="lint warnings become errors (exit 2 before sending)")
    add("--max-in-flight", type=int, default=2, help="concurrent requests (default 2; keep it low)")
    add("--env-file", type=Path, help="KEY=VALUE file to read ELEVENLABS_API_KEY from")
    add("--dry-run", action="store_true", help="print lint, requests and the meta that would be written; send nothing")
    return parser.parse_args()


def lint(lines: list[ScriptLine], direction: Direction, strict: bool, only: list[str]) -> None:
    count = 0
    for line in (line for line in lines if not only or line.id in only):
        for text in dict.fromkeys([line.spoken, *line.forms]):
            for problem in lint_text(text, direction.model, direction.language, direction.tags):
                print(f"{'ERROR' if strict else 'WARN'} lint {line.id}: {problem}  ({text})")
                count += 1
    if count and strict:
        print(f"error: {count} lint problems (--strict); fix the script or drop --strict", file=sys.stderr)
        sys.exit(2)
    if not count:
        print("lint: no problems")


def plan(lines: list[ScriptLine], direction: Direction, args: argparse.Namespace) -> dict[str, tuple[list[Attempt], int]]:
    planned = {}
    for index, line in enumerate(lines):
        if args.only and line.id not in args.only:
            continue
        wanted = args.hero_takes if line.id in args.hero else args.takes
        slots = take_slots(line, wanted, args.until_pass, args.per_form, args.retakes)
        planned[line.id] = (plan_line(lines, index, direction, args.prefix, slots, args.seed), wanted)
    return planned


def print_dry_run(planned: dict[str, tuple[list[Attempt], int]], direction: Direction, args: argparse.Namespace) -> None:
    url = f"{eleven.API_ROOT}/text-to-speech/{direction.voice_id}/with-timestamps?output_format={direction.output_format}"
    characters = requests = 0
    for line_id, (attempts, wanted) in planned.items():
        if args.until_pass:
            forms = len({attempt.form_index for attempt in attempts})
            print(f"ladder {line_id}: {forms} form(s), up to {len(attempts)} takes, stop at {wanted} passing")
        for attempt in attempts:
            if existing_audio(args.out, attempt.name):
                print(f"skip {attempt.name}: already on disk")
                continue
            body = dict(attempt.body)
            if args.stitch and requests:
                body["previous_request_ids"] = ["<request ids of up to 3 previous lines' first takes>"]
            print(f"POST {url}  ->  {attempt.name}{audio_suffix(direction.output_format)} + .json + .meta.json")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            meta = meta_for(attempt, direction, {"request_id": "<response header>", "character_cost": "<response header>"}, args.script)
            print(f"meta (would write {attempt.name}.meta.json): {json.dumps(meta, ensure_ascii=False)}")
            characters += len(attempt.text)
            requests += 1
    bound = "up to " if args.until_pass else ""
    print(f"dry run: {bound}{requests} requests, {bound}{characters} characters billed (approx.)")


def record_plain(session: Session, attempts: list[Attempt], workers: int) -> None:
    pending = [attempt for attempt in attempts if not existing_audio(session.out, attempt.name)]
    for attempt in attempts:
        if attempt not in pending:
            print(f"skip {attempt.name}: already on disk")

    def one(attempt: Attempt) -> None:
        path, meta, message = record(attempt, session.key, session.out, session.direction, session.script)
        session.say(message)
        session.account(meta if path else None)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, pending))


def record_stitched(session: Session, planned: dict[str, tuple[list[Attempt], int]]) -> None:
    history: list[str] = []
    for attempts, _ in planned.values():
        for attempt in attempts:
            if history:
                attempt.body["previous_request_ids"] = history[-3:]
            if existing_audio(session.out, attempt.name):
                print(f"skip {attempt.name}: already on disk")
                meta = read_meta(session.out, attempt.name)
            else:
                path, meta, message = record(attempt, session.key, session.out, session.direction, session.script)
                session.say(message)
                session.account(meta if path else None)
            if attempt is attempts[0] and meta.get("request_id"):
                history.append(meta["request_id"])


def main() -> int:
    args = parse_args()
    lines = TypeAdapter(list[ScriptLine]).validate_json(args.script.read_text())
    missing_text = [line.id for line in lines if line.text is None and not line.forms]
    if missing_text:
        sys.exit(f"error: lines without text or forms: {', '.join(missing_text)}")
    unknown = (set(args.only) | set(args.hero)) - {line.id for line in lines}
    if unknown:
        sys.exit(f"error: --only/--hero ids not in script: {', '.join(sorted(unknown))}")
    direction = resolve(args)
    if args.stitch and direction.model.startswith("eleven_v3"):
        sys.exit("error: request stitching is not available on eleven_v3")
    audio_suffix(direction.output_format)
    for warning in direction.warnings:
        print(f"WARN {warning}")
    if not args.no_lint:
        lint(lines, direction, args.strict, args.only)
    planned = plan(lines, direction, args)
    if args.stitch and any(len(attempts) > 1 for attempts, _ in planned.values()):
        print("WARN --stitch chains only each line's first take; use --takes 1 for long-form chunks")
    if args.dry_run:
        print_dry_run(planned, direction, args)
        return 0
    eleven.load_env_file(args.env_file)
    args.out.mkdir(parents=True, exist_ok=True)
    session = Session(eleven.require_key(), args.out, direction, args.script, args.qa_stt)
    workers = max(1, args.max_in_flight)
    if args.stitch:
        record_stitched(session, planned)
    elif args.until_pass:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda item: run_ladder(session, *item), planned.values()))
    else:
        record_plain(session, [attempt for attempts, _ in planned.values() for attempt in attempts], workers)
    print(f"characters charged (from response headers): {session.cost:.0f}")
    print(f"{session.failures} requests failed" if session.failures else "all requests succeeded")
    return 1 if session.failures else 0


if __name__ == "__main__":
    sys.exit(main())
