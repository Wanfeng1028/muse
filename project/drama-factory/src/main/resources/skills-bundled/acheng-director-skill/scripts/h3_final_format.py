"""Final, non-destructive H3 formatting pass and acceptance gate.

This module deliberately does not rewrite creative detail. It normalizes only
line endings/trailing whitespace and rejects prompts whose reference, shot,
speech, or global audio structure cannot be proven from production data.
"""
from __future__ import annotations

import re
import argparse
import hashlib
import json
from pathlib import Path
import sys

from h3_contract import english_word_count


BASE_FIELDS = ("integrated_multimodal_description", "overall_soundscape", "non_diegetic_music")
REF_FIELDS = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)
TASKS = {
    "keyframe completion",
    "reference generation",
    "video editing",
    "video continuation",
    "audio reuse",
    "audio reference",
}
LABEL_PATTERN = r"<(?:Subject|Picture|Video|Audio) [1-9]\d*>"
MEDIA_PATTERN = r"<(?:Picture|Video|Audio) [1-9]\d*>"
VISUAL_RELATIONS = {"fully_preserved", "partially_preserved", "attribute_transfer", "weak_reference"}
AUDIO_RELATIONS = {"fully_copy", "partially_copy", "reference", "weak_reference"}


class H3FormatError(ValueError):
    """Raised when a final H3 prompt cannot pass its deterministic format gate."""


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise H3FormatError(message)


def normalize_h3_prompt(text: str) -> str:
    """Apply the only automatic rewrite allowed after creative compilation.

    The body, numbers, engineering parameters, labels, punctuation and
    dialogue are preserved byte-for-byte except for line ending and trailing
    whitespace normalization.
    """
    _need(isinstance(text, str) and text.strip(), "H3 prompt must contain text")
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")) + "\n"


def _sections(text: str):
    matches = list(re.finditer(r"^([a-z_]+):[ \t]*\n", text, re.M))
    return [(match.group(1), match.start(), match.end(), matches[index + 1].start() if index + 1 < len(matches) else len(text))
            for index, match in enumerate(matches)]


def _section(text: str, name: str) -> str:
    for current, _, start, end in _sections(text):
        if current == name:
            return text[start:end].rstrip()
    raise H3FormatError(f"missing H3 section: {name}")


def _sentence_count(value: str) -> int:
    # Decimal points in 35.0, 0.3x, 4.2 kHz and similar engineering values
    # are not sentence boundaries. Quoted punctuation still counts when it
    # closes a natural-language sentence.
    return len(re.findall(r"(?<!\d)[.!?](?!\d)(?=\s|$|[`\"'”’)])", value))




def _check_shots(body: str, shot_count: int, duration_seconds=None) -> None:
    headers = [(int(number), whole) for whole, number in re.findall(r"(?m)^(\[Shot (\d+)\].*)$", body)]
    _need([number for number, _ in headers] == list(range(1, shot_count + 1)),
          "H3 shots must be numbered consecutively from [Shot 1]")
    _need(not re.search(r"(?m)^\[Shot \d+:\s", body),
          "H3 shot headers must not contain an inline time-range metadata block")
    _need(not re.search(r"(?m)^\[Shot 1\]\s+At\s", body),
          "[Shot 1] must not begin with a cut timestamp")
    previous = 0.0
    for number in range(2, shot_count + 1):
        match = re.search(rf"(?m)^\[Shot {number}\] At (\d{{2}}):([0-5]\d)\.(\d{{3}}),", body)
        _need(match is not None,
              f"Shot {number} must carry its cut time after the header")
        cut = int(match[1]) * 60 + int(match[2]) + int(match[3]) / 1000
        _need(cut > previous and (duration_seconds is None or cut < duration_seconds),
              f"Shot {number} cut must increase strictly within this Segment duration")
        previous = cut


def _check_speech(text: str, speech_expectations) -> None:
    tags = re.findall(r"<d>\[([A-Za-z]+)\] (.*?)</d>", text, re.S)
    for language, spoken in tags:
        _need(language and spoken.strip(), "every H3 dialogue tag needs a language and non-empty source text")
    for speaker, language, source_text in speech_expectations:
        _need(f"({speaker})" in text, f"speaker {speaker} is missing from the final H3 prompt")
        _need(f"<d>[{language}]" in text, f"speaker {speaker} is missing its language-tagged dialogue")
        # A cross-cut utterance can be split by <scenetrans>; each source part
        # remains literal and is checked by the production contract.
        pieces = re.sub(r"<scenetrans>|<cutoff>", "", source_text)
        _need(pieces in text, f"source dialogue for {speaker} was altered or omitted")
        # The speaker marker, a speech verb, and the literal source line must
        # form one local, auditable unit.  This prevents a prompt from listing
        # all speaker IDs in a distant preamble while leaving the actual line
        # ambiguous to H3.  The generous window allows long delivery clauses
        # and cross-cut continuity text without touching creative content.
        speech_pattern = (
            rf"\({re.escape(speaker)}\)[\s\S]{{0,900}}?"
            rf"\b(?:says|speaks|shouts|yells|whispers|replies|responds|exclaims|asks|sings)\b"
            rf"[\s\S]{{0,900}}?<d>\[{re.escape(language)}\]\s+"
            rf"(?:<scenetrans>|<cutoff>)*{re.escape(pieces)}(?:<scenetrans>|<cutoff>)*</d>"
        )
        _need(re.search(speech_pattern, text) is not None,
              f"speaker {speaker} must be locally bound to a speech verb and its literal dialogue")


def _check_reference_structure(text, reference_labels, subject_labels, shot_count):
    definitions = _section(text, "subject_definitions")
    media = set(reference_labels)
    _need(media and all(re.fullmatch(MEDIA_PATTERN, label) for label in media),
          "Ref2VA needs real media references; Subject labels alone are not sources")
    entries = {}
    for line in definitions.splitlines():
        if not line.strip():
            continue
        match = re.match(rf"^({LABEL_PATTERN})\s+is\s+\S", line)
        _need(match is not None, "reference definition must begin with <Label N> is ...")
        label = match[1]
        _need(label not in entries, "duplicate reference definition: " + label)
        entries[label] = line
    _need(set(subject_labels) <= set(entries), "Subject definition missing")
    for label, line in entries.items():
        if label.startswith("<Subject"):
            _need(bool(set(re.findall(MEDIA_PATTERN, line)) & media),
                  label + " must cite a registered real media source in its definition")
            _need(not re.search(r"<Audio [1-9]\d*>", line), "visual Subject must use Picture/Video sources, not Audio")
    retention = _section(text, "retention_analysis")
    retained = set()
    for line in retention.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(rf"({LABEL_PATTERN})(?: \(([^\n]+)\))?: ([a-z_]+) - (\S.*)", line)
        _need(match is not None, "retention must use <Label N> (scope): relationship - detail, not for")
        label, scope, relationship, _ = match.groups()
        _need(label in entries and label not in retained, "retention object missing or duplicated: " + label)
        _need(relationship in (AUDIO_RELATIONS if label.startswith("<Audio") else VISUAL_RELATIONS),
              "retention relationship does not match reference type: " + label)
        _need(not re.search(r"\(S[1-9]\d*\)", line), "speaker IDs do not belong in retention_analysis")
        if label.startswith("<Subject"):
            shots = [int(n) for n in re.findall(r"\[Shot (\d+)\]", scope or "")]
            _need(shots and all(1 <= n <= shot_count for n in shots), "Subject retention needs valid Shot appearances")
        retained.add(label)
    _need(retained == set(entries), "each standalone definition needs exactly one retention entry")


def _check_dialogue_events(body, expectations):
    events = list(re.finditer(r"<d>\[([A-Za-z]+)\] (.*?)</d>", body, re.S))
    _need(body.count("<d>") == body.count("</d>") == len(events), "malformed or unbalanced dialogue tags")
    seen, actual = [], []
    previous = 0
    for event in events:
        context = body[previous:event.start()]
        # A marker in an earlier shot cannot establish the speaker for this one.
        context = re.split(r"\[Shot \d+\]", context)[-1]
        bindings = list(re.finditer(r"\((S[1-9]\d*(?:,S[1-9]\d*)*)\)", context))
        _need(bindings, "every dialogue event needs a local stable speaker ID")
        binding = bindings[-1]
        _need(re.search(r"\b(?:says|speaks|shouts|yells|whispers|replies|responds|exclaims|asks|sings|screams|continues)\b",
                        context[binding.end():], re.I), "dialogue speaker must be locally bound to a speech verb")
        for speaker in binding[1].split(","):
            if speaker not in seen:
                _need(speaker == f"S{len(seen) + 1}", "speaker numbering must start at S1 in first-vocal-event order")
                seen.append(speaker)
        spoken = re.sub(r"<scenetrans>|<cutoff>", "", event[2])
        _need("<" not in spoken and ">" not in spoken, "unsupported markup inside dialogue")
        actual.append((binding[1], event[1], spoken))
        previous = event.end()
    if expectations is not None:
        expected = [(s, lang, re.sub(r"<scenetrans>|<cutoff>", "", words))
                    for s, lang, words in expectations]
        _need(actual == expected, "dialogue events differ from the approved ordered speaker/language/verbatim manifest")


def validate_h3_format(text: str, *, mode: str, shot_count: int,
                       reference_labels=(), subject_labels=(),
                       speech_expectations=None, minimum_words: int = 0,
                       duration_seconds=None) -> None:
    """Validate a compiled prompt without changing any creative content."""
    _need(mode in {"Ref2VA", "T2VA", "I2VA", "FL2VA", "L2VA"}, "unsupported H3 mode")
    _need(shot_count > 0, "at least one Shot is required")
    _need(not re.search(r"\b(?:CHAR|SCENE|PROP)_[A-Za-z0-9_]+\b", text),
          "internal asset IDs belong in the manifest, not final H3 text")
    expected = REF_FIELDS if mode == "Ref2VA" else BASE_FIELDS
    fields = tuple(name for name, *_ in _sections(text))
    _need(fields == expected, f"H3 section order mismatch: expected {expected}, got {fields}")
    _need(all(_section(text, field).strip() for field in fields), "H3 fields must not be empty")
    body_name = "detailed_description" if mode == "Ref2VA" else "integrated_multimodal_description"
    body = _section(text, body_name)
    _check_shots(body, shot_count, duration_seconds)
    allowed = set(reference_labels) | set(subject_labels)
    labels = set(re.findall(r"<(?:Subject|Picture|Video|Audio) [1-9]\d*>", text))
    _need(labels <= allowed, "final H3 prompt contains an unresolved reference label")
    if mode == "Ref2VA":
        _need(text[:_sections(text)[0][1]].strip() == "", "Ref2VA must begin with subject_definitions, without a prose wrapper")
        summary = _section(text, "summary")
        match = re.match(r"^\[([^\]]+)\]\s+", summary)
        _need(match is not None, "Ref2VA summary needs a bracketed task prefix")
        tasks = match.group(1).split(" + ")
        _need(tasks and len(tasks) == len(set(tasks)) and set(tasks) <= TASKS,
              "Ref2VA summary contains an unsupported or duplicate task prefix")
        _need(english_word_count(body) >= minimum_words,
              f"Ref2VA detailed_description is below the minimum of {minimum_words} English words")
        _check_reference_structure(text, reference_labels, subject_labels, shot_count)
        for task, kind in (("keyframe completion", "<Picture"), ("video editing", "<Video"),
                           ("video continuation", "<Video"), ("audio reuse", "<Audio"), ("audio reference", "<Audio")):
            _need(task not in tasks or any(label.startswith(kind) for label in reference_labels),
                  "task prefix has no matching media source: " + task)
    else:
        expected_refs = {"T2VA": [], "I2VA": ["<Picture 1>"], "FL2VA": ["<Picture 1>", "<Picture 2>"], "L2VA": ["<Picture 1>"]}[mode]
        _need(list(reference_labels) == expected_refs and not subject_labels, "base mode reference mapping mismatch")
    _check_speech(text, speech_expectations or ())
    _check_dialogue_events(body, speech_expectations)
    soundscape = _section(text, "overall_soundscape")
    music = _section(text, "non_diegetic_music")
    _need("\n\n" not in soundscape and "\n\n" not in music, "global sound fields must use continuous paragraphs")
    _need("<d>" not in soundscape + music, "dialogue belongs only in the shot timeline")
    if soundscape != "N/A":
        _need(1 <= _sentence_count(soundscape) <= 4,
              "overall_soundscape must be one continuous paragraph of 1–4 English sentences")
    if music != "N/A":
        _need(1 <= _sentence_count(music) <= 3,
              "non_diegetic_music must contain 1–3 English sentences")


def finalize_h3_prompt(text: str, **kwargs) -> str:
    """Normalize then validate the final H3 prompt before it is delivered."""
    normalized = normalize_h3_prompt(text)
    validate_h3_format(normalized, **kwargs)
    return normalized


def validate_h3_file(path, contract, base_dir=None, *, allow_legacy_fixture=False):
    """Read back final bytes and bind acceptance to files, not host-written PASS claims.

    The sidecar is an input manifest owned by the director, not another source of
    creative prose. Reference content/identity still requires human inspection.
    """
    path = Path(path)
    base = Path(base_dir) if base_dir is not None else path.parent
    raw = path.read_bytes()
    if contract.get("expected_prompt_sha256"):
        _need(hashlib.sha256(raw).hexdigest() == contract["expected_prompt_sha256"], "H3 changed after binding compilation")
    text = normalize_h3_prompt(raw.decode("utf-8-sig"))
    _need(isinstance(contract, dict), "H3 check manifest must be an object")
    mode = contract["mode"]
    duration = float(contract["duration_seconds"])
    _need(0 < duration < float("inf"), "finite positive Segment duration required")
    _need(isinstance(contract.get("speech_expectations"), list),
          "approved ordered speech_expectations required (use [] only for no dialogue)")
    refs, evidence, labels = contract.get("references", []), [], []
    for ref in refs:
        label = ref["label"]
        _need(re.fullmatch(MEDIA_PATTERN, label) is not None and label not in labels,
              "media label invalid or duplicated")
        source = (base / ref["file"]).resolve()
        _need(source.is_file() and source.stat().st_size > 0, "missing or empty reference media: " + str(source))
        allowed = {"Picture": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"},
                   "Video": {".mp4", ".mov", ".mkv", ".webm", ".avi"},
                   "Audio": {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".mp4", ".mov"}}
        kind = label.split()[0][1:]
        _need(source.suffix.lower() in allowed[kind], "reference must be media, not an asset prompt or JSON: " + str(source))
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        _need(ref.get("sha256") == digest, "reference SHA-256 missing or stale: " + label)
        _need(bool(ref.get("role")), "reference role required: " + label)
        from reference_bindings import inspect_media
        inspect_media(source, label, digest)
        labels.append(label)
        evidence.append({"label": label, "file": ref["file"], "sha256": digest, "role": ref["role"]})
    minimum = int(contract.get("minimum_words", 0))
    if mode == "Ref2VA":
        from math import ceil
        floor = max(2000, ceil(duration * 200))
        legacy = allow_legacy_fixture and contract.get("profile") == "legacy_fixture"
        _need(legacy or minimum >= floor, f"Ref2VA manifest minimum must be at least {floor}")
    validate_h3_format(text, mode=mode, shot_count=contract["shot_count"],
                       reference_labels=labels, subject_labels=contract.get("subject_labels", []),
                       speech_expectations=contract["speech_expectations"], minimum_words=minimum,
                       duration_seconds=duration)
    for field, expected in contract.get("reference_sections", {}).items():
        _need(_section(text, field) == expected.rstrip(), "reference meaning differs from binding snapshot: " + field)
    body = _section(text, "detailed_description" if mode == "Ref2VA" else "integrated_multimodal_description")
    return {"format_pass": "PASSED", "validator": "h3_final_format/4.3.6",
            "file": path.name, "sha256": hashlib.sha256(raw).hexdigest(),
            "contract_sha256": hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
            "mode": mode, "duration_seconds": duration, "shot_count": contract["shot_count"],
            "english_words": english_word_count(body), "minimum_words": minimum,
            "dialogue_count": len(contract["speech_expectations"]), "references": evidence,
            "input_revision": contract.get("input_revision"), "visual_status": "UNVERIFIED",
            "scope": "final-file structural validation; not creative, visual or audio acceptance"}


def file_contract(production, segment, references):
    """Adapt the existing production truth into check inputs; never copy its prose."""
    from h3_contract import detail_policy, speech_map
    speakers = speech_map(production, segment)
    shots = {shot["id"]: shot for shot in production["shots"]}
    policy = detail_policy(production, segment)
    speech = [[speakers[line.get("character_id", line["speaker_name"])], line["language"], line["text"]]
              for sid in segment["shot_ids"] for line in shots[sid]["dialogues"]]
    result = {"mode": segment["mode"], "duration_seconds": float(segment["generation_clip_duration"]),
            "shot_count": len(segment["shot_ids"]), "references": references,
            "subject_labels": [s["label"] for s in segment.get("subjects", [])],
            "speech_expectations": speech, "minimum_words": policy["minimum_words"], "profile": policy["profile"]}
    if segment["mode"] == "Ref2VA":
        from h3_contract import remap_speech_references
        from prompt_delivery import expand_prompt
        definitions = [r for r in segment["references"] if not r.get("source_only")] + segment.get("subjects", [])
        result["reference_sections"] = {field: expand_prompt(remap_speech_references("\n".join(r[key] for r in definitions), production, segment), production.get("prompt_bindings"))
                                        for field, key in (("subject_definitions", "definition"), ("retention_analysis", "retention"))}
    return result


def main():
    parser = argparse.ArgumentParser(description="Read-only final-file H3 gate; never rewrites prompt content.")
    parser.add_argument("prompt", type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8-sig"))
        report = validate_h3_file(args.prompt, contract, args.contract.parent)
        result = 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        report = {"format_pass": "FAILED", "file": str(args.prompt), "error": str(exc), "visual_status": "UNVERIFIED"}
        result = 1
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        # Evidence is revisioned too; an old receipt must never describe new bytes.
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
    print(text)
    return result


if __name__ == "__main__":
    sys.exit(main())
