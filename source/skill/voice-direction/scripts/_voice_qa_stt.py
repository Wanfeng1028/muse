"""Speech-to-text check for voice_qa.py: Scribe or faster-whisper, homophone-aware diff, repeats, spoken tags, leaks, events."""
import difflib
import functools
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import _voice_audio as audio
import _voice_eleven as eleven
import _voice_text as text_tools

WHISPER_RATE = 16000


@dataclass
class Transcript:
    text: str
    events: list[str] = field(default_factory=list)


Transcriber = Callable[[Path, int], Transcript]


def scribe_transcriber(key: str, model: str, language: str | None) -> Transcriber:
    def transcribe(path: Path, attempt: int) -> Transcript:
        data = {"model_id": model, "tag_audio_events": "true"}
        if language:
            data["language_code"] = language
        mime = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"
        files = {"file": (path.name, path.read_bytes(), mime)}
        reply = eleven.send("POST", f"{eleven.API_ROOT}/speech-to-text", key, f"  {path.name}: ", data=data, files=files)
        if not reply.ok:
            raise RuntimeError(f"Scribe HTTP {reply.status}: {reply.error}")
        body = reply.json()
        events = [word.get("text", "") for word in body.get("words", []) if word.get("type") == "audio_event"]
        return Transcript(body.get("text", ""), events)

    return transcribe


@functools.cache
def _whisper_model(name: str) -> object:
    from faster_whisper import (
        WhisperModel,  # optional: voice_qa.py re-runs itself with it installed
    )

    return WhisperModel(name, device="cpu", compute_type="int8")


def whisper_transcriber(model: str, language: str | None) -> Transcriber:
    def transcribe(path: Path, attempt: int) -> Transcript:
        samples = audio.decode_mono(path, rate=WHISPER_RATE)
        temperature = 0.0 if attempt == 0 else 0.6
        segments, _ = _whisper_model(model).transcribe(  # type: ignore[attr-defined]
            samples, language=language, beam_size=5, temperature=temperature, condition_on_previous_text=False
        )
        spoken = " ".join(segment.text.strip() for segment in segments)
        return Transcript(spoken, re.findall(r"[\[(][^\])]*[\])]", spoken))

    return transcribe


def load_allowances(path: Path | None, language: str) -> dict[str, set[str]]:
    if not path:
        return {}
    raw: dict[str, list[str]] = json.loads(path.read_text())

    def join(value: str) -> str:
        return " ".join(text_tools.normalize_spoken(value, language))

    return {join(expected): {join(heard) for heard in alternatives} for expected, alternatives in raw.items()}


@dataclass
class Comparison:
    match: bool
    missing: list[str]
    extra: list[str]
    leaks: list[str]
    spoken_tags: list[str]


EVENT_PATTERN = re.compile(r"\([^)]*\)|\[[^\]]*\]")


def _is_leak(expected_part: list[str], heard_part: list[str]) -> bool:
    if len(expected_part) != 1 or len(heard_part) != 1:
        return False
    want, got = expected_part[0], heard_part[0]
    return got != want and (got.endswith(want) or got.startswith(want))


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def compare(heard: str, expected: str, language: str, allowances: dict[str, set[str]]) -> Comparison:
    want = text_tools.normalize_spoken(expected, language)
    got = text_tools.normalize_spoken(EVENT_PATTERN.sub(" ", heard), language)
    missing: list[str] = []
    extra: list[str] = []
    leaks: list[str] = []
    for operation, first, last, heard_first, heard_last in difflib.SequenceMatcher(a=want, b=got, autojunk=False).get_opcodes():
        if operation == "equal":
            continue
        expected_part, heard_part = want[first:last], got[heard_first:heard_last]
        if "".join(expected_part) == "".join(heard_part) or " ".join(heard_part) in allowances.get(" ".join(expected_part), set()):
            continue
        missing += expected_part
        extra += heard_part
        if (operation == "insert" and first in (0, len(want))) or _is_leak(expected_part, heard_part):
            leaks += heard_part
    heard_plain = {re.sub(r"[^a-z]", "", text_tools.fold(word)) for word in heard.split()}
    expected_plain = {re.sub(r"[^a-z]", "", text_tools.fold(word)) for word in text_tools.words(expected)}
    spoken_tags = sorted((text_tools.tag_words(expected) & heard_plain) - expected_plain)
    return Comparison(not missing and not extra, missing, extra, leaks, spoken_tags)


def _settled(hits: int, misses: int, repeats: int) -> bool:
    majority = repeats // 2 + 1
    return (hits and not misses) or misses >= majority or hits >= repeats - majority + 1


def verify(path: Path, expected: str, language: str, transcriber: Transcriber, repeats: int,
           allowances: dict[str, set[str]], judge_short: bool) -> dict:
    count = text_tools.syllables(expected, language)
    verdict_on = judge_short or count > 2
    runs: list[dict] = []
    hits = misses = 0
    for attempt in range(max(1, repeats if verdict_on else 1)):
        transcript = transcriber(path, attempt)
        comparison = compare(transcript.text, expected, language, allowances)
        runs.append({"heard": transcript.text, "events": transcript.events, **comparison.__dict__})
        hits, misses = hits + comparison.match, misses + (not comparison.match)
        if _settled(hits, misses, repeats):
            break
    result = {
        "transcripts": [run["heard"] for run in runs],
        "misses": misses,
        "runs": len(runs),
        "syllables": count,
        "spoken_tags": _unique([tag for run in runs for tag in run["spoken_tags"]]),
        "leaks": _unique([word for run in runs for word in run["leaks"]]),
        "events": _unique([event for run in runs for event in run["events"]]),
        "missing": runs[-1]["missing"],
        "extra": runs[-1]["extra"],
    }
    if not verdict_on:
        return {**result, "status": "na", "reason": f"stt verdict skipped ({count} syllables; heard {runs[0]['heard']!r})"}
    majority = repeats // 2 + 1
    failed = misses >= majority or (repeats == 1 and misses)
    if failed:
        return {**result, "status": "fail", "reason": f"stt heard {runs[-1]['heard']!r} ({misses}/{len(runs)} misses)"}
    return {**result, "status": "pass"}
