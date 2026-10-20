#!/usr/bin/env python3
"""Apply fixes.json and keywords.json to words.json and write words.js for the caption engine.

fixes.json maps a raw transcribed token to its correction; an empty string drops the token.
A key written as `token@time` fixes only the word that starts at that time, for tokens like
`that` that are misheard once but correct everywhere else. Timestamps are never touched.

keywords.json is an array of words to keep in the accent colour. An entry matches case-insensitively,
ignoring punctuation; `word@time` flags only the one occurrence.

Also writes captions.srt and captions.vtt from the same phrases, for platforms that index uploaded
caption files. words.json is already shifted to the edit by trim_take.py, so the cue times match the
video after a trim.
"""

import json
import sys
from pathlib import Path

PHRASE_MAX_WORDS = 5
# transcript.txt prints times to two decimals, so a typed time is at most 5ms off
TIME_TOLERANCE = 0.006
PUNCTUATION = ".,!?;:\"'()"


def split_phrases(words):
    """Group words into caption phrases. Mirrors transcribe.split_phrases."""
    phrases, current = [], []
    for word in words:
        current.append(word)
        if len(current) >= PHRASE_MAX_WORDS or word["t"][-1] in ".,?!":
            phrases.append(current)
            current = []
    if current:
        phrases.append(current)
    return phrases


def parse_key(key):
    """Split `token@time` into (token, time); a plain token returns (token, None)."""
    token, separator, time = key.rpartition("@")
    if not separator or not token:
        return key, None
    try:
        return token, float(time)
    except ValueError:
        return key, None


def starts_at(word, time):
    return time is None or abs(word["s"] - time) < TIME_TOLERANCE


def bare(token):
    return token.strip(PUNCTUATION).lower()


def load_json(path, expected_type, example):
    """Return the parsed file, a default when it is absent, or None after printing the error."""
    if not path.is_file():
        return expected_type()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"{path} is not valid JSON: {e}", file=sys.stderr)
        print("Next: fix the JSON syntax, then re-run build_captions.py", file=sys.stderr)
        return None
    if not isinstance(data, expected_type):
        print(f"{path} must look like {example}", file=sys.stderr)
        print(f"Next: rewrite {path.name} in that shape, then re-run build_captions.py", file=sys.stderr)
        return None
    return data


def clock(seconds, separator):
    """Format seconds as HH:MM:SS,mmm (SRT) or HH:MM:SS.mmm (VTT)."""
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{ms:03d}"


def caption_cues(phrases):
    """One cue per phrase; a cue stays up until the next phrase, mirroring renderCaptions."""
    cues = []
    for i, phrase in enumerate(phrases):
        start = phrase[0]["s"]
        end = phrase[-1]["e"] + 0.6
        if i + 1 < len(phrases):
            end = min(end, phrases[i + 1][0]["s"])
        cues.append((start, max(end, start + 0.1), " ".join(word["t"] for word in phrase)))
    return cues


def write_caption_files(work, phrases):
    cues = caption_cues(phrases)
    srt = "".join(f"{i}\n{clock(start, ',')} --> {clock(end, ',')}\n{text}\n\n"
                  for i, (start, end, text) in enumerate(cues, 1))
    vtt = "WEBVTT\n\n" + "".join(f"{clock(start, '.')} --> {clock(end, '.')}\n{text}\n\n"
                                 for start, end, text in cues)
    (work / "captions.srt").write_text(srt, encoding="utf-8")
    (work / "captions.vtt").write_text(vtt, encoding="utf-8")
    return len(cues)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: build_captions.py <work-dir>", file=sys.stderr)
        return 1

    work = Path(sys.argv[1])
    words_path = work / "words.json"
    if not words_path.is_file():
        print(f"No words.json in {work}", file=sys.stderr)
        print("Next: run transcribe.py with --outdir pointing at this directory", file=sys.stderr)
        return 1

    fixes = load_json(work / "fixes.json", dict, '{"San": "Sun", "that@50.22": "data"}')
    keywords = load_json(work / "keywords.json", list, '["Java", "Kafka@12.40"]')
    if fixes is None or keywords is None:
        return 1
    words = json.loads(words_path.read_text(encoding="utf-8"))

    # Timed keys go first so `that@50.22` wins over a plain `that`
    parsed_fixes = sorted(((parse_key(key), value) for key, value in fixes.items()), key=lambda f: f[0][1] is None)
    used_fixes = set()
    applied = 0
    fixed = []
    for word in words:
        replacement = word["t"]
        for (token, time), value in parsed_fixes:
            if word["t"] == token and starts_at(word, time):
                replacement = value
                used_fixes.add((token, time))
                break
        if replacement != word["t"]:
            applied += 1
        if replacement:
            fixed.append({**word, "t": replacement})

    parsed_keywords = [parse_key(entry) for entry in keywords if isinstance(entry, str) and bare(entry)]
    used_keywords = set()
    marked = 0
    for word in fixed:
        for token, time in parsed_keywords:
            if bare(word["t"]) == bare(token) and starts_at(word, time):
                word["k"] = 1
                used_keywords.add((token, time))
                marked += 1
                break

    phrases = split_phrases(fixed)
    (work / "words.js").write_text("window.PHRASES=" + json.dumps(phrases) + ";", encoding="utf-8")
    cues = write_caption_files(work, phrases)

    unused_fixes = [key for key in fixes if parse_key(key) not in used_fixes]
    unused_keywords = [entry for entry in keywords if isinstance(entry, str) and parse_key(entry) not in used_keywords]
    print(f"{len(fixed)} words · {len(phrases)} phrases · {applied} fixes applied · {marked} keywords flagged"
          f" · {cues} cues in captions.srt + captions.vtt")
    if unused_fixes:
        print(f"  unmatched fixes: {', '.join(unused_fixes)} — tokens must match transcript.txt exactly, punctuation included; @time must be the word's start")
    if unused_keywords:
        print(f"  unmatched keywords: {', '.join(unused_keywords)} — match ignores case and punctuation; @time must be the word's start")
    print(f"Next: write the shot list (load references/scene-blocks.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
