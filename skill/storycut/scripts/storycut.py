#!/usr/bin/env python3
"""StoryCut: deterministic transcript preparation and verified cut-list exports.

Claude is the editor; this script never uses an LLM or pretends to rank clips.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


TIME_TOKEN = r"(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}|(?:\d{1,2}:)?\d{1,2}:\d{2}"
TIMING_LINE = re.compile(rf"^\s*({TIME_TOKEN})\s*-->\s*({TIME_TOKEN})(?:\s+.*)?$")
TXT_LINE = re.compile(rf"^\s*\[\s*({TIME_TOKEN})\s*(?:-|-->|to)\s*({TIME_TOKEN})\s*\]\s*(.+)$", re.I)
SPACE = re.compile(r"\s+")
TRANSCRIPT_SUFFIXES = {".srt", ".vtt", ".txt"}


class StoryCutError(Exception):
    """A user-fixable validation or processing problem."""


def seconds(token: str) -> float:
    chunks = token.replace(",", ".").split(":")
    try:
        if len(chunks) == 3:
            hour, minute, sec = chunks
            value = int(hour) * 3600 + int(minute) * 60 + float(sec)
        elif len(chunks) == 2:
            minute, sec = chunks
            value = int(minute) * 60 + float(sec)
        else:
            raise ValueError("Invalid timecode")
        if value < 0 or not 0 <= float(sec) < 60 or not 0 <= int(minute) < 60:
            raise ValueError("Invalid minute/second range")
        return round(value, 3)
    except ValueError as exc:
        raise StoryCutError(f"Invalid timecode: {token}") from exc


def timestamp(value: float) -> str:
    millis = round(value * 1000)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, fraction = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{fraction:03}"


def segment(start: float, end: float, text: str) -> dict:
    content = SPACE.sub(" ", text.strip())
    if end <= start or not content:
        raise StoryCutError(f"Invalid empty/negative-duration segment at {timestamp(start)}")
    return {"start": round(start, 3), "end": round(end, 3), "text": content}


def parse_subtitles(content: str) -> list[dict]:
    """Read SRT/VTT cues. Cue indices and VTT headers/notes are ignored."""
    normalized = content.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    chunks = re.split(r"\n\s*\n", normalized)
    items: list[dict] = []
    for block in chunks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or lines[0].upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        index = next((i for i, line in enumerate(lines) if TIMING_LINE.match(line)), None)
        if index is None:
            continue
        match = TIMING_LINE.match(lines[index])
        assert match
        body = " ".join(lines[index + 1 :])
        # Keep speech, strip subtitle markup rather than accidentally treating tags as words.
        body = re.sub(r"<[^>]*>", "", body)
        if body.strip():
            items.append(segment(seconds(match[1]), seconds(match[2]), body))
    if not items:
        raise StoryCutError("No timestamped subtitle cues were found.")
    return items


def parse_timed_txt(content: str) -> list[dict]:
    items: list[dict] = []
    for line_no, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            continue
        match = TXT_LINE.match(line)
        if not match:
            raise StoryCutError(
                f"Text line {line_no} needs an explicit range, e.g. "
                "[00:00:01.000 - 00:00:04.000] Spoken words."
            )
        items.append(segment(seconds(match[1]), seconds(match[2]), match[3]))
    if not items:
        raise StoryCutError("Transcript is empty.")
    return items


def transcribe_media(path: Path, model_name: str, language: str | None) -> list[dict]:
    if not shutil.which("ffmpeg"):
        raise StoryCutError("FFmpeg is missing. Install it to process audio/video files.")
    if importlib.util.find_spec("faster_whisper") is None:
        raise StoryCutError(
            "faster-whisper is missing. Install with: python3 -m pip install faster-whisper "
            "(the speech model also downloads on first use)."
        )
    from faster_whisper import WhisperModel  # type: ignore[import-not-found]

    with tempfile.TemporaryDirectory(prefix="storycut-") as temp:
        audio = Path(temp) / "mono.wav"
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-vn", "-ac", "1", "-ar", "16000", "-y", str(audio)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise StoryCutError(f"FFmpeg could not decode the media: {result.stderr.strip()[-500:]}")
        print(f"Transcribing locally with faster-whisper model '{model_name}'...", file=sys.stderr)
        model = WhisperModel(model_name, device="auto", compute_type="int8")
        output, _info = model.transcribe(str(audio), language=language, vad_filter=True)
        items = [segment(part.start, part.end, part.text) for part in output if part.text.strip()]
    if not items:
        raise StoryCutError("No speech was detected. Check the audio and language.")
    return items


def prepare(input_path: Path, out_dir: Path, model_name: str, language: str | None) -> Path:
    if not input_path.is_file():
        raise StoryCutError(f"Input file not found: {input_path}")
    suffix = input_path.suffix.lower()
    if suffix in {".srt", ".vtt"}:
        items = parse_subtitles(input_path.read_text(encoding="utf-8-sig"))
    elif suffix == ".txt":
        items = parse_timed_txt(input_path.read_text(encoding="utf-8-sig"))
    else:
        items = transcribe_media(input_path, model_name, language)
    items.sort(key=lambda item: (item["start"], item["end"]))
    for i, item in enumerate(items):
        item["id"] = f"s{i + 1:04d}"
    data = {"format_version": 1, "source": input_path.name, "timing": "approximate speech cues",
            "segments": items}
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "transcript.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(items)} timed segments -> {output}")
    return output


def _normalized(value: str) -> str:
    return SPACE.sub(" ", value.strip()).casefold()


def validate(transcript_path: Path, draft_path: Path) -> tuple[dict, list[str]]:
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    segments = transcript.get("segments", [])
    if not isinstance(segments, list) or not segments:
        raise StoryCutError("Transcript has no segments.")
    positions = {item["id"]: i for i, item in enumerate(segments)}
    if len(positions) != len(segments):
        raise StoryCutError("Transcript contains duplicate segment IDs.")
    proposed = draft.get("clips")
    if not isinstance(proposed, list) or not proposed:
        raise StoryCutError("Draft needs a non-empty 'clips' list.")
    sorted_clips = sorted(proposed, key=lambda c: c.get("order", -1))
    if [clip.get("order") for clip in sorted_clips] != list(range(1, len(proposed) + 1)):
        raise StoryCutError("Clip orders must be unique consecutive integers starting at 1.")
    used: set[str] = set()
    warnings: list[str] = []
    exported: list[dict] = []
    for clip in sorted_clips:
        number = clip["order"]
        ids = clip.get("segment_ids")
        if not isinstance(ids, list) or not ids or not all(isinstance(x, str) for x in ids):
            raise StoryCutError(f"Clip {number} needs a non-empty segment_ids list.")
        if any(item not in positions for item in ids):
            raise StoryCutError(f"Clip {number} uses unknown segment IDs: {[x for x in ids if x not in positions]}")
        indexes = [positions[item] for item in ids]
        if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
            raise StoryCutError(f"Clip {number}: segment IDs must be consecutive and in source order.")
        if used.intersection(ids):
            raise StoryCutError(f"Clip {number} reuses a segment already selected by an earlier clip.")
        used.update(ids)
        selected = [segments[idx] for idx in indexes]
        start = float(selected[0]["start"])
        end = float(selected[-1]["end"])
        if end <= start:
            raise StoryCutError(f"Clip {number}: invalid time range.")
        text = " ".join(item["text"] for item in selected)
        quote = clip.get("quote", "")
        if quote and _normalized(quote) not in _normalized(text):
            raise StoryCutError(f"Clip {number}: quote is not an exact contiguous excerpt of its source text.")
        if end - start > 120:
            warnings.append(f"Clip {number} is {end - start:.1f}s long; consider a shorter cut.")
        exported.append({"order": number, "title": clip.get("title", f"Clip {number}"),
                         "role": clip.get("role", "story"), "start_seconds": start,
                         "end_seconds": end, "start": timestamp(start), "end": timestamp(end),
                         "duration_seconds": round(end - start, 3), "segment_ids": ids,
                         "quote": quote, "reason": clip.get("reason", ""),
                         "source_text": text})
    total = round(sum(clip["duration_seconds"] for clip in exported), 3)
    target = draft.get("target_seconds")
    if isinstance(target, (float, int)) and target > 0 and abs(total - target) > max(15, target * .2):
        warnings.append(f"Selected speech totals {total:.1f}s vs target {target}s; revise or explain.")
    output = {"format_version": 1, "source": transcript.get("source", ""),
              "title": draft.get("title", "StoryCut"), "audience": draft.get("audience", ""),
              "goal": draft.get("goal", ""), "target_seconds": target,
              "total_seconds": total, "editor_notes": draft.get("editor_notes", ""),
              "clips": exported, "warnings": warnings}
    return output, warnings


def export(cutlist: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cutlist.json").write_text(json.dumps(cutlist, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    with (out_dir / "cutlist.csv").open("w", newline="", encoding="utf-8") as file:
        fields = ["order", "title", "role", "start", "end", "duration_seconds", "segment_ids", "quote", "reason"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for clip in cutlist["clips"]:
            writer.writerow({key: ",".join(clip[key]) if key == "segment_ids" else clip.get(key, "")
                             for key in fields})
    lines = [f"# {cutlist['title']}", "", f"**Source:** {cutlist['source']}",
             f"**Audience:** {cutlist['audience']}", f"**Goal:** {cutlist['goal']}",
             f"**Selected footage:** {cutlist['total_seconds']:.1f} seconds", "",
             "| Order | Source in–out | Role | Moment | Why keep it |", "|---|---|---|---|---|"]
    for clip in cutlist["clips"]:
        clean = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {clip['order']} | {clip['start']}–{clip['end']} | {clean(clip['role'])} | "
                     f"{clean(clip['title'])} | {clean(clip['reason'])} |")
    if cutlist.get("editor_notes"):
        lines.extend(["", "## Editorial notes", "", cutlist["editor_notes"]])
    if cutlist["warnings"]:
        lines.extend(["", "## Warnings", "", *(f"- {item}" for item in cutlist["warnings"])])
    lines.extend(["", "*Timings are based on source speech segments and should be refined at edit boundaries.*", ""])
    (out_dir / "cutlist.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Exported cutlist.md, cutlist.csv, cutlist.json -> {out_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check optional media processing dependencies")
    prep = commands.add_parser("prepare", help="Build a verified timed transcript")
    prep.add_argument("input", type=Path)
    prep.add_argument("--out", type=Path, required=True)
    prep.add_argument("--model", default="base", help="faster-whisper model; default base")
    prep.add_argument("--language", default=None, help="ISO language code; auto-detected if omitted")
    check = commands.add_parser("validate", help="Verify clip IDs/quotes and export cut list")
    check.add_argument("transcript", type=Path)
    check.add_argument("draft", type=Path)
    check.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            print(f"Python: {sys.version.split()[0]}")
            print(f"FFmpeg: {'found' if shutil.which('ffmpeg') else 'MISSING (required for media)'}")
            print(f"faster-whisper: {'found' if importlib.util.find_spec('faster_whisper') else 'MISSING (required for media)'}")
            print("Timed SRT/VTT/TXT input works without FFmpeg or faster-whisper.")
        elif args.command == "prepare":
            prepare(args.input, args.out, args.model, args.language)
        else:
            output, warnings = validate(args.transcript, args.draft)
            export(output, args.out)
            for warning in warnings:
                print(f"WARNING: {warning}", file=sys.stderr)
    except (StoryCutError, FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
