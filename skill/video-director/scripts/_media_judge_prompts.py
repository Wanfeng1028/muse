"""Prompt templates and per-mode reports for media_judge.py. Every format is one line so answers can be parsed."""
import argparse
from collections.abc import Callable
from pathlib import Path

from _media_judge_core import Answer, field_number, field_text, save

VO_BRIEF = "a warm, natural voiceover for a short promotional film"
RESTATE = (
    "You are a cold viewer. You watch this video once, with the sound off, as it would autoplay in a social feed. "
    "You know nothing about the product. Reply in ONE line, exactly: MESSAGE: <the film's message in one sentence> | "
    "PRODUCT: <what is offered and to whom, or unclear> | CONFUSING: <moments you could not follow, with m:ss, or none>"
)
TargetPath = Callable[[argparse.Namespace, Path, str], Path]


def vo_take(text: str, brief: str, accent: str | None) -> str:
    accent_slot = f"{accent} / other (name it)" if accent else "name the accent"
    return (
        f"Voice director check for {brief}. Intended script (bracketed tags such as [softly] are delivery directions "
        f'and must NOT be spoken): "{text}".\nReply in ONE line, exactly: TRANSCRIPT: <what you hear> | ERRORS: '
        "<mispronunciations, spoken tags, missing/extra words, glitches, or none> | "
        f"ACCENT: <{accent_slot}> | DELIVERY 1-10: <n> <3-8 words why>"
    )


def pairwise(brief: str) -> str:
    return (
        f"Two takes of the same line for {brief}. Which is better (more natural, better emphasis and rhythm, fewer "
        "artifacts)? Take A is the first audio, take B the second. Reply in ONE line: WINNER: A or B | <10-20 words why>"
    )


def blind_splice(seconds: float) -> str:
    return (
        f"This is a {seconds:.0f}-second music excerpt. Some excerpts contain an editor's splice (two different parts of "
        "a song joined), others are untouched. Is there a splice? Reply in ONE line, exactly: SPLICE: yes/no | "
        "WHERE: m:ss or none | NOTICEABLE 1-10: <n> | WHY: <one sentence>"
    )


def music_fit(brief: str) -> str:
    return (
        f"You are a strict music supervisor. Listen to the whole track. The film: {brief}\nReply in ONE line, exactly: "
        "INSTRUMENTS: <list> | STYLE: <genre and cultural feel> | INTRO: tender/medium/busy | LIFT AT: <m:ss or none> | "
        "VOCALS: none/wordless/with words | GENERIC STOCK 1-10: <n> | WARMTH 1-10: <n> | ENERGY 1-10: <n> | "
        "VO SPACE 1-10: <n> | FIT 1-10: <n> | VERDICT: <one sentence>"
    )


def chunk(vo_brief: str) -> str:
    return (
        "This is a short excerpt of a music track. In ONE line (max 30 words): instruments audible, energy 1-10, any "
        f"vocals or shouts, any hit/fill/stop/riser, and whether it would sit well under {vo_brief}. "
        "Format: instruments | energy N | vocals | events | VO-friendly yes/no"
    )


def report(args: argparse.Namespace, answers: list[Answer], target: TargetPath) -> int:
    reporters = {
        "vo-take": report_takes, "pairwise": report_pairwise, "blind-splice": report_blind,
        "music-fit": report_music, "chunks": report_chunks, "restate": report_restate, "ask": report_ask,
    }
    return reporters[args.mode](args, [answer for answer in answers if not answer.error], target)


def report_takes(args: argparse.Namespace, answers: list[Answer], target: TargetPath) -> int:
    for answer in answers:
        save(target(args, answer.request.meta["path"], ".judge.txt"), [f"{answer.request.key}  {answer.text}"])
    for answer in sorted(answers, key=lambda a: -(field_number(a.text, "DELIVERY") or 0)):
        errors = field_text(answer.text, "ERRORS") or "?"
        print(f"{answer.request.key:<20} DELIVERY {field_number(answer.text, 'DELIVERY') or '?'}  ERRORS: {errors}")
    return 0


def report_pairwise(args: argparse.Namespace, answers: list[Answer], target: TargetPath) -> int:
    first, second = args.files
    wins = {first: 0, second: 0}
    lines = []
    for answer in answers:
        letter = field_text(answer.text, "WINNER")[:1].upper()
        a, b = answer.request.meta["a"], answer.request.meta["b"]
        winner = a if letter == "A" else b if letter == "B" else None
        if winner:
            wins[winner] += 1
        lines.append(f"{answer.request.key} (A={a.name}, B={b.name}): {answer.text}")
    lines.append(f"TALLY: {first.name} {wins[first]} - {wins[second]} {second.name}")
    save(target(args, first, f".vs.{second.stem}.judge.txt"), lines)
    print(lines[-1])
    return 0


def report_blind(args: argparse.Namespace, answers: list[Answer], target: TargetPath) -> int:
    lines = [f"{a.request.key}: {a.text}" for a in sorted(answers, key=lambda a: a.request.key)]
    rates: dict[str, float] = {}
    has_verdicts = False
    for role in ("edited", "control"):
        group = [a for a in answers if a.request.meta["role"] == role]
        verdicts = [field_text(a.text, "SPLICE").lower() for a in group]
        has_verdicts = has_verdicts or any(verdicts)
        yes = sum(v.startswith("yes") for v in verdicts)
        scores = [s for a in group if (s := field_number(a.text, "NOTICEABLE") or field_number(a.text, "SCORE")) is not None]
        mean = f"{sum(scores) / len(scores):.1f}" if scores else "-"
        rates[role] = yes / len(group) if group else 0.0
        lines.append(f"{role.upper()}: splice yes {yes}/{len(group)}, mean score {mean} ({len(group)} answers)")
    if not has_verdicts:
        lines.append("no SPLICE answers: compare the mean scores of the edited clip and the control")
        save(target(args, args.files[0], ".blind-splice.judge.txt"), lines)
        print("\n".join(lines[-3:]))
        return 0
    gap = rates["edited"] - rates["control"]
    verdict = "FAIL edit is detectable" if gap >= args.margin else "PASS edit not distinguishable from the control"
    lines.append(f"{verdict} (yes-rate gap {gap:+.2f}, threshold {args.margin})")
    save(target(args, args.files[0], ".blind-splice.judge.txt"), lines)
    print("\n".join(lines[-3:]))
    return 1 if gap >= args.margin else 0


def report_music(args: argparse.Namespace, answers: list[Answer], target: TargetPath) -> int:
    for answer in answers:
        save(target(args, answer.request.meta["path"], ".music-fit.judge.txt"), [f"{answer.request.key}  {answer.text}"])
    for answer in sorted(answers, key=lambda a: -(field_number(a.text, "FIT") or 0)):
        print(f"FIT {field_number(answer.text, 'FIT') or '?':>4}  {answer.request.key:<28} {field_text(answer.text, 'VERDICT')}")
    return 0


def report_chunks(args: argparse.Namespace, answers: list[Answer], target: TargetPath) -> int:
    for path in args.files:
        rows = sorted((a for a in answers if a.request.meta["path"] == path), key=lambda a: a.request.meta["start"])
        lines = [f"{a.request.meta['start']:7.2f}s  {a.text}" for a in rows]
        save(target(args, path, ".chunks.judge.txt"), lines)
        print("\n".join(lines))
    return 0


def report_restate(args: argparse.Namespace, answers: list[Answer], target: TargetPath) -> int:
    for answer in answers:
        save(target(args, answer.request.meta["path"], ".restate.judge.txt"), [f"{answer.request.key}  {answer.text}"])
        print(f"{answer.request.key}: {answer.text}")
    print("Compare MESSAGE with the intended message. If it hesitates, too much moves at once. Verify any motion claim in strips.")
    return 0


def report_ask(args: argparse.Namespace, answers: list[Answer], target: TargetPath) -> int:
    for answer in answers:
        save(target(args, answer.request.meta["path"], ".ask.judge.txt"), [answer.text])
        print(answer.text)
    return 0
