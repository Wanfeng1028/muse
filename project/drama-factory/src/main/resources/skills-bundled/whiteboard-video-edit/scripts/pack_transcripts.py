# Ported from browser-use/video-use (MIT License, Copyright (c) 2026 Browser Use)
# https://github.com/browser-use/video-use at 9575612f066aa517354790a645fd90f9f95a743b
# Source file: helpers/pack_transcripts.py. Adapted: a per-take hints block (fillers,
# cut-off words that mark false starts, repeated word runs that mark retakes) so the
# rough-cut decisions start from the evidence instead of a re-read of the raw JSON.
"""Pack every Scribe transcript in <edit-dir>/transcripts/ into one small text view.

Words are grouped into phrase lines, breaking on any silence >= 0.5 s or a speaker
change, each prefixed with its [start-end] source time. This is the file to read when
choosing what to keep: word-boundary precision from text alone, at a tenth of the tokens
of the raw JSON. Drill into exact word times with `rough_cut.py words`.

Output: <edit-dir>/takes_packed.md

Usage:
    python3 pack_transcripts.py --edit-dir <dir> [--silence-threshold 0.5]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Standalone hesitation tokens only. "like", "you know", "so" carry meaning often enough
# that removing them is a judgment call, so they are left to the reader.
FILLERS = {"um", "umm", "uh", "uhh", "uhm", "erm", "er", "ah", "ahh", "hmm", "mm", "mhm", "eh"}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9']", "", text.lower())


def is_filler(w: dict) -> bool:
    return w.get("type") == "word" and norm(w.get("text", "")) in FILLERS


def is_cutoff(w: dict) -> bool:
    """Scribe marks a word the speaker broke off mid-way with a trailing dash ("has--")."""
    return w.get("type") == "word" and (w.get("text") or "").rstrip().endswith("-")


def fmt_t(seconds: float) -> str:
    return f"{seconds:06.2f}"


def fmt_dur(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds // 60)
    return f"{m}m {seconds - m * 60:04.1f}s"


def group_into_phrases(words: list[dict], silence_threshold: float = 0.5) -> list[dict]:
    phrases: list[dict] = []
    cur: list[dict] = []
    cur_speaker = None
    prev_end = None

    def flush() -> None:
        nonlocal cur, cur_speaker
        parts = []
        for w in cur:
            raw = (w.get("text") or "").strip()
            if not raw:
                continue
            if w.get("type") == "audio_event" and not raw.startswith("("):
                raw = f"({raw})"
            parts.append(raw)
        if parts:
            text = " ".join(parts)
            for p in (",", ".", "?", "!"):
                text = text.replace(f" {p}", p)
            phrases.append({"start": cur[0]["start"], "end": cur[-1].get("end", cur[-1]["start"]),
                            "text": text, "speaker_id": cur_speaker})
        cur = []
        cur_speaker = None

    for w in words:
        t = w.get("type", "word")
        if t == "spacing":
            if w.get("start") is not None and w.get("end") is not None \
                    and w["end"] - w["start"] >= silence_threshold:
                flush()
            continue
        if w.get("start") is None:
            continue
        spk = w.get("speaker_id")
        if cur_speaker is not None and spk is not None and spk != cur_speaker:
            flush()
        if prev_end is not None and w["start"] - prev_end >= silence_threshold:
            flush()
        if not cur:
            cur_speaker = spk
        cur.append(w)
        prev_end = w.get("end", w["start"])
    flush()
    return phrases


def repeated_runs(words: list[dict], min_len: int = 3, window_s: float = 20.0) -> list[tuple]:
    """Word runs (>= min_len words) said twice within window_s: retake candidates.
    Returns (first_start, first_end, second_start, second_end, text), longest first."""
    toks = [w for w in words if w.get("type") == "word" and not is_filler(w)]
    keys = [norm(w["text"]) for w in toks]
    found: dict[tuple, tuple] = {}
    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            if toks[j]["start"] - toks[i]["start"] > window_s:
                break
            n = 0
            while j + n < len(toks) and i + n < j and keys[i + n] == keys[j + n] and keys[i + n]:
                n += 1
            if n >= min_len and (i == 0 or j == 0 or keys[i - 1] != keys[j - 1]):
                span = (toks[i]["start"], toks[i + n - 1]["end"], toks[j]["start"], toks[j + n - 1]["end"])
                found[span] = span + (" ".join(t["text"] for t in toks[i:i + n]),)
    return sorted(found.values(), key=lambda r: -(r[1] - r[0]))


def hints(words: list[dict]) -> list[str]:
    out = []
    fillers = [w for w in words if is_filler(w)]
    if fillers:
        out.append("  fillers: " + ", ".join(f"'{w['text'].strip()}' {w['start']:.2f}" for w in fillers))
    cut = [w for w in words if is_cutoff(w)]
    if cut:
        out.append("  cut-off words (false start candidates): "
                   + ", ".join(f"'{w['text'].strip()}' {w['start']:.2f}-{w['end']:.2f}" for w in cut))
    events = [w for w in words if w.get("type") == "audio_event"]
    if events:
        out.append("  audio events: " + ", ".join(f"{w['text'].strip()} {w['start']:.2f}" for w in events))
    reps = repeated_runs(words)
    if reps:
        out.append("  repeated runs (retake candidates, judge each; many are legitimate):")
        for a0, a1, b0, b1, text in reps[:25]:
            out.append(f"    '{text}'  [{fmt_t(a0)}-{fmt_t(a1)}] again [{fmt_t(b0)}-{fmt_t(b1)}]")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Pack Scribe transcripts into takes_packed.md")
    ap.add_argument("--edit-dir", type=Path, required=True)
    ap.add_argument("--silence-threshold", type=float, default=0.5)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()

    edit_dir = args.edit_dir.expanduser().resolve()
    files = sorted(p for p in (edit_dir / "transcripts").glob("*.json") if not p.name.endswith(".source.json"))
    if not files:
        sys.exit(f"no transcripts in {edit_dir / 'transcripts'}")

    lines = ["# Packed transcripts", "",
             f"Phrase lines break on silence >= {args.silence_threshold:.1f}s or a speaker change. "
             "Times are SOURCE seconds.", ""]
    total_phrases = 0
    for jp in files:
        words = json.loads(jp.read_text()).get("words", [])
        phrases = group_into_phrases(words, args.silence_threshold)
        total_phrases += len(phrases)
        span = phrases[-1]["end"] - phrases[0]["start"] if phrases else 0.0
        lines.append(f"## {jp.stem}  (speech span {fmt_dur(span)}, {len(phrases)} phrases)")
        if not phrases:
            lines += ["  _no speech detected_", ""]
            continue
        for p in phrases:
            spk = p.get("speaker_id")
            tag = f" S{str(spk).replace('speaker_', '')}" if spk is not None else ""
            lines.append(f"  [{fmt_t(p['start'])}-{fmt_t(p['end'])}]{tag} {p['text']}")
        h = hints(words)
        if h:
            lines += ["", "  Hints:"] + h
        lines.append("")

    out = args.output or (edit_dir / "takes_packed.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"packed {len(files)} transcript(s), {total_phrases} phrases -> {out} ({out.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
