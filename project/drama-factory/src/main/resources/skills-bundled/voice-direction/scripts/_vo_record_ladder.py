"""--until-pass for vo_record.py: check each take with the voice_qa gates and walk the retake ladder until enough pass."""
import threading
from dataclasses import dataclass, field
from pathlib import Path

import _voice_qa_stt as stt
from _vo_record_take import Attempt, existing_audio, read_meta, record, write_meta
from _vo_record_voice import Direction
from _voice_qa_checks import Thresholds, check_take


@dataclass
class Session:
    key: str
    out: Path
    direction: Direction
    script: Path
    qa_stt: str = "none"
    stt_model: str = "scribe_v2"
    limits: Thresholds = field(default_factory=Thresholds)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cost: float = 0.0
    failures: int = 0

    def say(self, message: str) -> None:
        with self.lock:
            print(message, flush=True)

    def account(self, meta: dict | None) -> None:
        with self.lock:
            if meta is None:
                self.failures += 1
                return
            self.cost += float(meta.get("character_cost") or 0)


def quality(session: Session, attempt: Attempt, path: Path) -> dict:
    language = session.direction.language
    report = check_take(path, attempt.name, session.direction.voice_id, attempt.line.spoken, language, session.limits)
    if session.qa_stt == "scribe" and language:
        transcriber = stt.scribe_transcriber(session.key, session.stt_model, language)
        try:
            report.checks["stt"] = stt.verify(path, attempt.line.spoken, language, transcriber, 3, {}, False)
        except RuntimeError as error:
            report.checks["stt"] = {"status": "fail", "reason": f"stt error: {error}"}
    return {"verdict": "pass" if report.passed else "fail", "reasons": report.failures, "checks": report.checks}


def judged(session: Session, attempt: Attempt, path: Path) -> dict:
    meta = read_meta(session.out, attempt.name)
    stale = session.qa_stt != "none" and "stt" not in meta.get("qa", {}).get("checks", {})
    if meta.get("qa") and not stale:
        return meta["qa"]
    result = quality(session, attempt, path)
    if meta:
        write_meta(session.out, attempt.name, {**meta, "qa": result})
    return result


def run_ladder(session: Session, attempts: list[Attempt], wanted: int) -> list[str]:
    passing: list[str] = []
    for attempt in attempts:
        path = existing_audio(session.out, attempt.name)
        if path is None:
            path, meta, message = record(attempt, session.key, session.out, session.direction, session.script)
            session.say(message)
            session.account(meta if path else None)
            if path is None:
                continue
        result = judged(session, attempt, path)
        form = f"form {attempt.form_index + 1} {attempt.text!r}"
        verdict = "PASS" if result["verdict"] == "pass" else "FAIL " + "; ".join(result["reasons"])
        session.say(f"  qa {attempt.name} ({form}): {verdict}")
        if result["verdict"] == "pass":
            passing.append(attempt.name)
        if len(passing) >= wanted:
            return passing
    session.say(f"WARN {attempts[0].line.id}: ladder exhausted with {len(passing)}/{wanted} passing takes; listen or edit the line")
    return passing
