#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2", "httpx>=0.27", "pydantic>=2"]
# ///
"""Automatic gates for voiceover takes, and a static screen plus blind listening page for casting voices.

Takes mode checks every take (pass / fail / n/a with a value):
  noise_floor_db   quietest 10% of Hann frames (1024/512 at 44.1 kHz) minus the loudest frame; fail above -62 dB.
                   n/a ("floor not measurable") when under 10% of frames are 35 dB below the peak (continuous speech).
  seconds          fail under 0.4 s (cut-off take); with text of 3+ words, fail outside expected +-30% (4.5 syllables/s
                   for es/pt/en, which varied less than words per minute on real takes; 150 wpm otherwise).
  lufs             R128 loudness (clips under 0.6 s looped 3x), true peak (fail above 0 dBTP), clipped samples (fail > 0).
  quiet_at_source  fail under -24 LUFS, or (3+ takes of a voice) more than 4 LU below that voice's median: a breathy read.
  stt              opt-in --stt scribe|whisper: transcript vs text (tags stripped, homophones allowed); a miss must repeat in
                   2 of 3 transcriptions to fail; spoken tags, context leaks and audio events are reported. 1-2 syllable
                   texts are report-only unless --stt-syllables.
Text per take: --text, else <take>.meta.json / <take>.json "text" (vo_record.py), else --script by line id.

Screen mode records probes per voice into <out>/<voice_id>-<probe#>.mp3, runs the offline checks, ranks voices by
worst probe floor (static above -65 dB), writes <out>/screen.json, <out>/screen.html and, with --blind, a lettered
page in <out>/blind/ with the letter-to-voice mapping in <out>/key.json (serve only blind/ to the listener).
"""
import argparse
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _voice_audio as audio  # noqa: E402
import _voice_eleven as eleven  # noqa: E402
import _voice_qa_screen as screen  # noqa: E402
import _voice_qa_stt as stt  # noqa: E402
from _voice_qa_checks import (  # noqa: E402
    TakeReport,
    Thresholds,
    apply_voice_medians,
    check_take,
)
from _voice_qa_page import write_blind, write_open  # noqa: E402
from _voice_qa_takes import resolve_takes  # noqa: E402

EXAMPLES = """examples:
  voice_qa.py out/vo/takes/*.mp3 --script script.json --language es --stt scribe --env-file .env.local
  voice_qa.py take.mp3 --text "hola." --language es --report out/vo/qa-one.json
  voice_qa.py --screen-voices --library "language=es&accent=colombian" --language es --blind --dry-run
  voice_qa.py --screen-voices ids.txt --language en --script script.json --blind --env-file .env"""
DEFAULT_PROBES = {"es": ["ma.", "mariposa."]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gate VO takes (noise floor, length, loudness, quiet at source, clipping, optional STT) or screen voices.",
        epilog=__doc__.split("\n\n", 1)[1] + "\n" + EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add = parser.add_argument
    add("takes", nargs="*", help="audio files or globs (mp3/wav)")
    add("--script", type=Path, help='script JSON [{"id","text"}] (vo_record.py format): text by line id; probes in screen mode')
    add("--prefix", default="", help="take name prefix before the line id, e.g. 'sofia-' (helps --script matching)")
    add("--text", help="intended text for every take given (usually one file)")
    add("--group-by", choices=["auto", "prefix", "folder", "none"], default="auto",
        help="voice grouping for quiet-at-source medians: auto = meta.json voice, script prefix, then folder; "
             "prefix = file name up to the first - or _")
    add("--language", help="ISO 639-1 code (es, pt, en...): homophones, syllables, STT language; required for --screen-voices")
    limits = parser.add_argument_group("thresholds")
    limits.add_argument("--max-floor-db", type=float, default=-62.0, help="noise floor gate (default -62)")
    limits.add_argument("--floor-percentile", type=float, default=10.0, help="quiet frames percentile (default 10)")
    limits.add_argument("--min-silence-fraction", type=float, default=0.10, help="floor n/a below this silent share (default 0.10)")
    limits.add_argument("--min-seconds", type=float, default=0.4, help="shortest acceptable take (default 0.4)")
    limits.add_argument("--sps", type=float, default=4.5, help="expected syllables/s for es, pt, en (default 4.5)")
    limits.add_argument("--wpm", type=float, default=150.0, help="expected pace for other languages (default 150)")
    limits.add_argument("--pause-seconds", type=float, default=0.25, help="expected extra per comma/stop inside a line (default 0.25)")
    limits.add_argument("--duration-tolerance", type=float, default=0.30, help="allowed duration error (default 0.30)")
    limits.add_argument("--max-true-peak", type=float, default=0.0,
                        help="true peak gate in dBTP (default 0.0: raw ElevenLabs takes peak up to -0.3 and vo_build limits them)")
    limits.add_argument("--quiet-lufs", type=float, default=-24.0, help="quiet at source below this (default -24)")
    limits.add_argument("--quiet-delta", type=float, default=4.0, help="LU below the voice median that counts as quiet (default 4)")
    speech = parser.add_argument_group("speech to text")
    speech.add_argument("--stt", choices=["scribe", "whisper", "none"], default="none", help="engine (default none)")
    speech.add_argument("--stt-model", default="scribe_v2", help="Scribe model (default scribe_v2)")
    speech.add_argument("--whisper-model", default="large-v3", help="faster-whisper model (default large-v3; installed on demand)")
    speech.add_argument("--stt-repeats", type=int, default=3, help="max transcriptions per take on a miss (default 3)")
    speech.add_argument("--allow", type=Path, help='known harmless misses JSON {"hay": ["i", "ai"]}')
    speech.add_argument("--stt-syllables", action="store_true", help="also give an STT verdict on 1-2 syllable texts")
    voices = parser.add_argument_group("screen voices")
    voices.add_argument("--screen-voices", nargs="?", const="", metavar="IDS_OR_FILE", help="ids (comma-separated) or a file")
    voices.add_argument("--library", help='shared-voices query, e.g. "language=es&accent=colombian&gender=female"')
    voices.add_argument("--max-voices", type=int, default=40, help="library candidates to screen (default 40)")
    voices.add_argument("--probes", nargs="+", help='probe texts (default for es: "ma." "mariposa."; else first 2 script lines)')
    voices.add_argument("--model", default="eleven_v4", help="TTS model for probes (default eleven_v4)")
    voices.add_argument("--stability", type=float, default=0.8, help="probe stability (default 0.8)")
    voices.add_argument("--similarity", type=float, default=0.75, help="probe similarity boost (default 0.75)")
    voices.add_argument("--context-before", help="unspoken framing sent as previous_text")
    voices.add_argument("--context-after", help="unspoken framing sent as next_text")
    voices.add_argument("--probe-takes", type=int, default=1, help="takes per probe (default 1)")
    voices.add_argument("--output-format", default="mp3_44100_128", help="probe output_format (default mp3_44100_128)")
    voices.add_argument("--screen-max-floor-db", type=float, default=-65.0, help="static above this on any probe (default -65)")
    voices.add_argument("--blind", action="store_true", help="also write a lettered blind page + key.json")
    voices.add_argument("--out", type=Path, default=Path("out/vo/screen"), help="screen folder (default out/vo/screen)")
    add("--max-in-flight", type=int, default=2, help="concurrent API requests (default 2, hard cap 3)")
    add("--env-file", type=Path, help="KEY=VALUE file with ELEVENLABS_API_KEY")
    add("--report", type=Path, help="JSON report (default out/vo/qa.json; screen mode: <out>/screen.json)")
    add("--report-only", action="store_true", help="exit 0 even when a take fails")
    add("--dry-run", action="store_true", help="print the API requests (STT, probes, library) without sending them")
    add("--verbose", action="store_true", help="print the ffmpeg binaries used")
    return parser.parse_args()


def thresholds(args: argparse.Namespace, max_floor_db: float | None = None) -> Thresholds:
    return Thresholds(
        max_floor_db=args.max_floor_db if max_floor_db is None else max_floor_db, floor_percentile=args.floor_percentile,
        min_silence_fraction=args.min_silence_fraction, min_seconds=args.min_seconds, wpm=args.wpm, sps=args.sps,
        pause_seconds=args.pause_seconds,
        duration_tolerance=args.duration_tolerance, max_true_peak=args.max_true_peak, quiet_lufs=args.quiet_lufs,
        quiet_delta=args.quiet_delta,
    )


def ensure_whisper(args: argparse.Namespace) -> None:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        if os.environ.get("VOICE_QA_WHISPER_REEXEC"):
            sys.exit("error: faster-whisper could not be installed; run with --stt scribe instead")
        print("faster-whisper not in the environment; re-running with `uv run --with faster-whisper`", flush=True)
        os.environ["VOICE_QA_WHISPER_REEXEC"] = "1"
        script = str(Path(__file__).resolve())
        os.execvp("uv", ["uv", "run", "--quiet", "--with", "faster-whisper>=1.1", "--script", script, *sys.argv[1:]])


def build_transcriber(args: argparse.Namespace) -> stt.Transcriber:
    if args.stt == "whisper":
        return stt.whisper_transcriber(args.whisper_model, args.language)
    eleven.load_env_file(args.env_file)
    return stt.scribe_transcriber(eleven.require_key(), args.stt_model, args.language)


def run_stt(reports: list[TakeReport], args: argparse.Namespace) -> None:
    pending = [report for report in reports if report.text]
    for report in reports:
        if not report.text:
            report.checks["stt"] = {"status": "na", "reason": "no text to compare"}
    if args.dry_run:
        for report in pending:
            target = "POST https://api.elevenlabs.io/v1/speech-to-text" if args.stt == "scribe" else f"faster-whisper {args.whisper_model}"
            fields = {"model_id": args.stt_model, "language_code": args.language, "tag_audio_events": "true"} if args.stt == "scribe" else {}
            print(f"dry run: {target} {json.dumps(fields)} file={report.file} (up to {args.stt_repeats}x)")
            report.checks["stt"] = {"status": "na", "reason": "dry run"}
        return
    if not args.language:
        sys.exit("error: --stt needs --language (or vo_record meta.json with a language)")
    transcriber = build_transcriber(args)
    allowances = stt.load_allowances(args.allow, args.language)

    def check(report: TakeReport) -> None:
        language = report.language or args.language
        try:
            report.checks["stt"] = stt.verify(Path(report.file), report.text or "", language, transcriber, args.stt_repeats,
                                              allowances, args.stt_syllables)
        except RuntimeError as error:
            report.checks["stt"] = {"status": "fail", "reason": f"stt error: {error}"}

    workers = 1 if args.stt == "whisper" else max(1, min(screen.HARD_MAX_IN_FLIGHT, args.max_in_flight))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(check, pending))


def summary_line(report: TakeReport) -> str:
    checks = report.checks
    floor = checks["noise_floor_db"]
    floor_text = f"floor {floor['value']:.1f}" if floor["status"] != "na" else "floor n/a"
    lufs = checks["lufs"]["value"]
    stt_check = checks.get("stt")
    stt_text = "" if not stt_check else {"pass": "  stt ok", "fail": "  stt MISS", "na": "  stt n/a"}[stt_check["status"]]
    reasons = f"  [{'; '.join(report.failures)}]" if report.failures else ""
    notes = [floor["reason"]] if floor["status"] == "na" else []
    if stt_check and stt_check.get("status") == "na" and stt_check.get("reason"):
        notes.append(stt_check["reason"])
    note_text = f"  ({'; '.join(notes)})" if notes and not report.failures else ""
    lufs_text = f"{lufs:.1f} LUFS" if lufs is not None else "- LUFS"
    verdict = "PASS" if report.passed else "FAIL"
    return f"{report.name:<22}{verdict}  {floor_text:<11} {checks['seconds']['value']:>6.2f}s  {lufs_text:>11}{stt_text}{reasons}{note_text}"


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {path}")


def takes_mode(args: argparse.Namespace) -> int:
    paths = [Path(match) for pattern in args.takes for match in (sorted(glob.glob(pattern)) or [pattern])]
    paths = [path for path in paths if path.suffix.lower() in audio.AUDIO_SUFFIXES]
    if not paths:
        sys.exit("error: no audio takes given (mp3/wav files or globs)")
    if args.stt == "whisper" and not args.dry_run:
        ensure_whisper(args)
    limits = thresholds(args)
    reports = [check_take(take.path, take.name, take.voice, take.text, take.language or args.language, limits)
               for take in resolve_takes(paths, args.script, args.prefix, args.text, args.group_by)]
    apply_voice_medians(reports, limits)
    if args.stt != "none":
        run_stt(reports, args)
    for report in reports:
        print(summary_line(report))
    failed = sum(not report.passed for report in reports)
    print(f"\n{len(reports) - failed} PASS, {failed} FAIL of {len(reports)} takes")
    payload = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": "takes",
               "thresholds": limits.__dict__, "stt": args.stt,
               "summary": {"takes": len(reports), "passed": len(reports) - failed, "failed": failed},
               "takes": [report.as_dict() for report in reports]}
    write_report(args.report or Path("out/vo/qa.json"), payload)
    return 1 if failed and not args.report_only else 0


LONG_PROBE_WORDS = 3


def warn_long_probes(probes: list[str]) -> None:
    """The floor is the quietest 10% of frames: a probe that is mostly speech puts that percentile inside the voice."""
    long = [probe for probe in probes if len(probe.split()) > LONG_PROBE_WORDS]
    if long:
        print(f"warning: {len(long)} probe(s) longer than {LONG_PROBE_WORDS} words; the floor may be measured inside speech "
              "and fail clean voices (one or two words with a full stop, e.g. 'ma.' 'mariposa.', leave silence to measure)", file=sys.stderr)


def probe_texts(args: argparse.Namespace) -> list[str]:
    if args.probes:
        warn_long_probes(args.probes)
        return args.probes
    if args.language in DEFAULT_PROBES:
        return DEFAULT_PROBES[args.language]
    if args.script:
        return [line.get("text") or line["forms"][0] for line in json.loads(args.script.read_text())[:2]]
    sys.exit("error: pass --probes (or --script) for languages other than es")


def screen_mode(args: argparse.Namespace) -> int:
    if not args.language:
        sys.exit("error: --screen-voices needs --language")
    if not args.screen_voices and not args.library:
        sys.exit("error: give voice ids or a file to --screen-voices, or --library QUERY")
    probes = probe_texts(args)
    base_body: dict = {"model_id": args.model, "language_code": args.language,
                       "voice_settings": {"stability": args.stability, "similarity_boost": args.similarity}}
    if args.context_before:
        base_body["previous_text"] = args.context_before
    if args.context_after:
        base_body["next_text"] = args.context_after
    candidates = screen.parse_voice_input(args.screen_voices) if args.screen_voices else []
    if args.dry_run:
        return screen_dry_run(args, candidates, probes, base_body)
    eleven.load_env_file(args.env_file)
    if args.library:
        candidates += screen.fetch_library(eleven.require_key(), args.library, args.max_voices)
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = screen.plan_probes(candidates, probes, args.probe_takes, args.out, base_body)
    pending = [job for job in jobs if not job.path.exists()]
    failures, cost = (screen.record_all(pending, eleven.require_key(), args.max_in_flight, args.output_format)
                      if pending else (0, 0.0))
    if cost:
        print(f"characters charged (from response headers): {cost:.0f}")
    limits = thresholds(args, args.screen_max_floor_db)
    reports: dict[str, list[TakeReport]] = {}
    for job in jobs:
        if job.path.exists():
            report = check_take(job.path, job.path.stem, job.voice.id, job.text, args.language, limits)
            reports.setdefault(job.voice.id, []).append(report)
    for voice_reports in reports.values():
        apply_voice_medians(voice_reports, limits)
    rows = screen.summarize(candidates, reports, args.screen_max_floor_db)
    screen.print_table(rows)
    complete = [row for row in rows if len(row["takes"]) == len(probes) * args.probe_takes]
    files = {(job.voice.id, job.probe): screen.probe_file(args.out, job.voice.id, job.probe, 0) for job in jobs}
    print(f"wrote {write_open(args.out, complete, probes, files)}")
    if args.blind and complete:
        page, key = write_blind(args.out, complete, probes, files)
        print(f"wrote {page} (serve only {page.parent}/ to the listener)\nwrote {key}")
    payload = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": "screen",
               "probes": probes, "request": base_body, "screen_max_floor_db": args.screen_max_floor_db, "voices": rows}
    write_report(args.report or args.out / "screen.json", payload)
    return 1 if failures and not args.report_only else 0


def screen_dry_run(args: argparse.Namespace, candidates: list[screen.Candidate], probes: list[str], base_body: dict) -> int:
    planned = len(candidates)
    if args.library:
        print(f"dry run: GET {screen.library_url(args.library, 0)} (more pages until {args.max_voices} voices)")
        planned += args.max_voices
    for voice in candidates[:3]:
        print(f"dry run: POST {screen.probe_url(voice.id, args.output_format)}")
        print(json.dumps({**base_body, "text": probes[0]}, ensure_ascii=False, indent=2))
    requests = planned * len(probes) * args.probe_takes
    characters = planned * args.probe_takes * sum(len(text) for text in probes)
    print(f"dry run: {planned} voices x {len(probes)} probes x {args.probe_takes} takes = {requests} requests, "
          f"{characters} characters (approx.); files in {args.out}/<voice_id>-<probe#>.mp3")
    return 0


def main() -> int:
    args = parse_args()
    audio.binary("ffmpeg", args.verbose)
    audio.binary("ffprobe", args.verbose)
    if args.screen_voices is not None or args.library:
        return screen_mode(args)
    return takes_mode(args)


if __name__ == "__main__":
    sys.exit(main())
