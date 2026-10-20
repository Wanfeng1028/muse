#!/usr/bin/env python3
"""Re-time an existing edit onto a retake of the same script.

  retime.py <old work> <new work>

Aligns the two transcripts word by word (difflib on normalised tokens), builds a monotonic time
map from the matched words, then rewrites every time in the old composition's TIMELINE block, its
NOCAP ranges and the @time keys in fixes.json / keywords.json onto the new take. The old SHOTS
markup carries over unchanged. Passages that differ between takes (ad-libs, cut sentences) are
listed, never silently mis-timed, so the agent can handle them by hand.

Run after transcribe.py / trim_take.py on the retake, and after fill_template.py has written the
new work's index.html. Then re-run build_captions.py in the new work.
"""

import argparse
import bisect
import difflib
import json
import re
import sys
from pathlib import Path

PUNCTUATION = ".,!?;:\"'()"
NUMBER = re.compile(r"-?(?:\d+(?:\.\d+)?|\.\d+)")
CALL = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*")
# A `t:` or `e:` key with a plain numeric value, as in terminal lines and SFX.push
KEYED_TIME = re.compile(r"(?<![\w$.])[te](\s*:\s*)(-?(?:\d+(?:\.\d+)?|\.\d+))")
NOCAP_LINE = re.compile(r"(?m)^const NOCAP = .*;$")

# Helper calls used in the TIMELINE block, with the positional arguments that are times rather
# than durations, strengths or pixel values — the signatures in templates/kinetic.html
TIME_ARGS = {
    "shot": {1, 2}, "faceCam": {1, 2}, "clip": {2, 3}, "broll": {2, 3},
    "hit": {0}, "slam": {1}, "rise": {1}, "pop": {1}, "stagger": {1}, "stamp": {1},
    "drift": {1, 2}, "kenBurns": {1, 2}, "lowerThird": {1, 2}, "ticker": {1, 2},
    "typer": {2, 3}, "counter": {3, 4}, "fromRight": {1}, "grow": {1}, "draw": {1},
    "check": {1}, "cross": {1}, "fadeOut": {1}, "slide": {3}, "chapter": {1, 2},
    "mood": {2, 3}, "look": {3, 4}, "point": {1, 2}, "bubble": {1, 2}, "send": {3},
    "presenter": {1, 2}, "presenterOff": {1},
}
# Raw GSAP calls take their position time as the last argument
GSAP_LAST_ARG = ("tl.to", "tl.fromTo", "tl.set", "tl.from", "tl.call")


def fmt(seconds):
    """Two decimals like transcript.txt, without trailing zeros."""
    text = f"{seconds:.2f}".rstrip("0").rstrip(".")
    return text if text else "0"


def normalise(token):
    return token.strip(PUNCTUATION).lower()


def mask_code(text):
    """True where a character sits inside a string or line comment, so it is never rewritten."""
    masked = [False] * len(text)
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if char in "\"'`":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == char:
                    break
                j += 1
            for k in range(i, min(j + 1, n)):
                masked[k] = True
            i = j + 1
        elif char == "/" and text[i:i + 2] == "//":
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                masked[k] = True
            i = j
        else:
            i += 1
    return masked


def split_args(text, open_paren, masked):
    """Split a call's arguments at top-level commas; return (arg spans, index past the ')')."""
    args, depth, arg_start, i, n = [], 0, open_paren + 1, open_paren, len(text)
    while i < n:
        if masked[i]:
            i += 1
            continue
        char = text[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                args.append((arg_start, i))
                return args, i + 1
        elif char == "," and depth == 1:
            args.append((arg_start, i))
            arg_start = i + 1
        i += 1
    return None, None


def retime_js(block, map_time):
    """Rewrite the times in a TIMELINE block; return (new block, how many were rewritten)."""
    masked = mask_code(block)
    edits = []

    def edit_number(start, end):
        token = block[start:end].strip()
        if not NUMBER.fullmatch(token):
            return
        lead = len(block[start:end]) - len(block[start:end].lstrip())
        edits.append((start + lead, start + lead + len(token), fmt(map_time(float(token)))))

    i = 0
    while i < len(block):
        if masked[i]:
            i += 1
            continue
        name = CALL.match(block, i)
        if name and block[name.end():].lstrip().startswith("("):
            open_paren = name.end() + len(block[name.end():]) - len(block[name.end():].lstrip())
            args, after = split_args(block, open_paren, masked)
            if args is None:
                break
            callee = name.group()
            positions = TIME_ARGS.get(callee)
            if positions is None and callee in GSAP_LAST_ARG:
                positions = {len(args) - 1}
            for position in positions or ():
                if position < len(args):
                    edit_number(*args[position])
            i = after
            continue
        i += 1

    # Keyed times inside object literals (terminal lines, SFX.push), skipping spans already done
    for match in re.finditer(KEYED_TIME, block):
        start = match.start(2)
        if masked[start] or any(start >= a and start < b for a, b, _ in edits):
            continue
        edit_number(match.start(2), match.end(2))

    for start, end, replacement in sorted(edits, reverse=True):
        block = block[:start] + replacement + block[end:]
    return block, len(edits)


def align(old_words, new_words):
    """Align on normalised tokens; return the matcher and a strictly increasing anchor list."""
    old_tokens = [normalise(word["t"]) for word in old_words]
    new_tokens = [normalise(word["t"]) for word in new_words]
    matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
    anchors = []
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            old_word, new_word = old_words[block.a + k], new_words[block.b + k]
            anchors.append((old_word["s"], new_word["s"]))
            anchors.append((old_word["e"], new_word["e"]))
    anchors.sort()
    return matcher, anchors


def monotonic(anchors):
    """Drop anything that would fold time backwards, so the map never runs in reverse."""
    mono = []
    for old_t, new_t in anchors:
        if mono and (old_t <= mono[-1][0] + 1e-9 or new_t <= mono[-1][1] + 1e-9):
            continue
        mono.append((old_t, new_t))
    return mono


def make_mapper(anchors):
    """Piecewise-linear map between the two takes, extrapolating from the edge segments."""
    anchors = monotonic(sorted(anchors))
    old_times = [old for old, _ in anchors]

    def map_time(t):
        if not anchors:
            return t
        if len(anchors) == 1:
            return max(0.0, t + anchors[0][1] - anchors[0][0])
        index = bisect.bisect_right(old_times, t) - 1
        index = min(max(index, 0), len(anchors) - 2)
        (o1, n1), (o2, n2) = anchors[index], anchors[index + 1]
        return max(0.0, n1 + (t - o1) * (n2 - n1) / (o2 - o1))

    return map_time


def differing_passages(matcher, old_words, new_words):
    """One entry per differing region: (old text, new text, old start, new start)."""
    passages = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        passages.append((" ".join(w["t"] for w in old_words[i1:i2]),
                         " ".join(w["t"] for w in new_words[j1:j2]),
                         old_words[i1]["s"] if i1 < i2 else None,
                         new_words[j1]["s"] if j1 < j2 else None))
    return passages


def extract(html, begin, end, work):
    if begin not in html or end not in html:
        print(f"{work}/index.html has no {begin.strip('/<!- ')} … {end.strip('/<!- ')} markers", file=sys.stderr)
        print("Next: keep the template's BEGIN/END markers when editing the shot list", file=sys.stderr)
        return None
    start = html.index(begin)
    return html[start:html.index(end, start) + len(end)]


def retime_key(key, map_time):
    """Rewrite the time in a `token@time` key; plain tokens and non-numeric @suffixes pass through."""
    token, separator, time = key.rpartition("@")
    if separator and token:
        try:
            return f"{token}@{fmt(map_time(float(time)))}"
        except ValueError:
            pass
    return key


def load_words(work):
    path = work / "words.json"
    if not path.is_file():
        print(f"No words.json in {work}", file=sys.stderr)
        print("Next: run transcribe.py (and trim_take.py) on that take first", file=sys.stderr)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-time an existing edit onto a retake of the same script.")
    parser.add_argument("old", type=Path, help="work directory of the finished edit")
    parser.add_argument("new", type=Path, help="work directory of the retake (transcribed, template filled)")
    args = parser.parse_args()

    old_words, new_words = load_words(args.old), load_words(args.new)
    if old_words is None or new_words is None:
        return 1
    old_html_path, new_html_path = args.old / "index.html", args.new / "index.html"
    if not old_html_path.is_file():
        print(f"No index.html in {args.old}", file=sys.stderr)
        print("Next: pass the work directory that holds the finished edit", file=sys.stderr)
        return 1
    if not new_html_path.is_file():
        print(f"No index.html in {args.new}", file=sys.stderr)
        print("Next: run fill_template.py for the retake first", file=sys.stderr)
        return 1
    old_html, new_html = old_html_path.read_text(encoding="utf-8"), new_html_path.read_text(encoding="utf-8")

    matcher, anchors = align(old_words, new_words)
    anchors = monotonic(anchors)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    if len(anchors) < 2:
        print(f"Only {matched} words match between the two transcripts — not a retake of the same script",
              file=sys.stderr)
        print("Next: re-time this edit by hand, or check the two work dirs hold the same script", file=sys.stderr)
        return 1
    map_time = make_mapper(anchors)

    shots = extract(old_html, "<!-- BEGIN SHOTS -->", "<!-- END SHOTS -->", args.old)
    timeline = extract(old_html, "// BEGIN TIMELINE", "// END TIMELINE", args.old)
    nocap = NOCAP_LINE.search(old_html)
    new_shots = extract(new_html, "<!-- BEGIN SHOTS -->", "<!-- END SHOTS -->", args.new)
    new_timeline = extract(new_html, "// BEGIN TIMELINE", "// END TIMELINE", args.new)
    if None in (shots, timeline, new_shots, new_timeline):
        return 1
    if not nocap:
        print(f"No `const NOCAP = …;` line in {args.old}/index.html", file=sys.stderr)
        print("Next: keep the template's NOCAP declaration just below // END TIMELINE", file=sys.stderr)
        return 1
    if not NOCAP_LINE.search(new_html):
        print(f"No `const NOCAP = …;` line in {args.new}/index.html", file=sys.stderr)
        print("Next: keep the template's NOCAP declaration just below // END TIMELINE", file=sys.stderr)
        return 1

    timeline, rewritten = retime_js(timeline, map_time)
    nocap_line = NUMBER.sub(lambda m: fmt(map_time(float(m.group()))), nocap.group())
    new_html = new_html.replace(new_shots, shots).replace(new_timeline, timeline)
    new_html = NOCAP_LINE.sub(lambda _: nocap_line, new_html, count=1)
    new_html_path.write_text(new_html, encoding="utf-8")

    remapped = []
    for name, shape in (("fixes.json", dict), ("keywords.json", list)):
        source = args.old / name
        if not source.is_file():
            continue
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, shape):
            print(f"{source} has an unexpected shape — copy it to the retake by hand", file=sys.stderr)
            continue
        if shape is dict:
            data = {retime_key(key, map_time): value for key, value in data.items()}
        else:
            data = [retime_key(entry, map_time) if isinstance(entry, str) else entry for entry in data]
        (args.new / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        remapped.append(name)

    print(f"retimed {matched} of {len(old_words)} old words ({len(new_words)} in the retake) · "
          f"{len(anchors)} anchors · {rewritten} times in the timeline · NOCAP remapped"
          + (f" · {', '.join(remapped)} remapped" if remapped else ""))
    old_take, new_take = args.old / "take.json", args.new / "take.json"
    if old_take.is_file() and new_take.is_file():
        old_duration = json.loads(old_take.read_text(encoding="utf-8")).get("duration")
        new_duration = json.loads(new_take.read_text(encoding="utf-8")).get("duration")
        if old_duration and new_duration:
            print(f"  duration: {old_duration:.2f}s → {new_duration:.2f}s")
    passages = differing_passages(matcher, old_words, new_words)
    if passages:
        print(f"  {len(passages)} passages differ between the takes — re-time or re-shoot these by hand:")
        for old_text, new_text, old_start, new_start in passages:
            old_side = f"old {old_start:.2f}s: \"{old_text}\"" if old_text else "old: —"
            new_side = f"new {new_start:.2f}s: \"{new_text}\"" if new_text else "new: —"
            print(f"    {old_side} → {new_side}")
    if matched < 10:
        print("  warning: very few matched words — check this is a retake of the same script")
    print(f"Next: review the differing passages, then run build_captions.py {args.new} and re-render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
