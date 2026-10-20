"""Offline take checks for voice_qa.py and vo_record.py --until-pass: noise floor, length, loudness, clipping, quiet at source."""
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import _voice_audio as audio
import _voice_text as text_tools

VOICED_CENTROID_HZ = 1500
SYLLABLE_LANGUAGES = {"es", "pt", "en"}


@dataclass(frozen=True)
class Thresholds:
    max_floor_db: float = -62.0
    floor_percentile: float = 10.0
    min_silence_fraction: float = 0.10
    min_seconds: float = 0.4
    wpm: float = 150.0
    sps: float = 4.5
    pause_seconds: float = 0.25
    duration_tolerance: float = 0.30
    max_true_peak: float = 0.0
    quiet_lufs: float = -24.0
    quiet_delta: float = 4.0


@dataclass
class TakeReport:
    file: str
    name: str
    voice: str
    text: str | None
    language: str | None
    checks: dict[str, dict] = field(default_factory=dict)

    @property
    def failures(self) -> list[str]:
        return [check.get("reason", name) for name, check in self.checks.items() if check["status"] == "fail"]

    @property
    def passed(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict:
        return {**self.__dict__, "verdict": "pass" if self.passed else "fail", "reasons": self.failures}


def check_floor(samples, limits: Thresholds) -> dict:
    measured = audio.noise_floor(samples, limits.floor_percentile)
    result = {"value": measured.floor_db, "silence_fraction": measured.silence_fraction, "quiet_centroid_hz": measured.quiet_centroid_hz}
    if measured.floor_db is None:
        return {**result, "status": "na", "reason": "too short to measure a floor"}
    if measured.silence_fraction < limits.min_silence_fraction:
        return {**result, "status": "na", "reason": "floor not measurable (not enough silence to measure)"}
    if measured.floor_db > limits.max_floor_db:
        voiced = measured.quiet_centroid_hz is not None and measured.quiet_centroid_hz < VOICED_CENTROID_HZ
        hint = f"quiet frames centre at {measured.quiet_centroid_hz:.0f} Hz: soft speech or breath, not hiss? listen" if voiced else "static"
        return {**result, "status": "fail", "reason": f"noise floor {measured.floor_db} dB > {limits.max_floor_db} ({hint})"}
    return {**result, "status": "pass"}


def expected_seconds(text: str, language: str | None, limits: Thresholds) -> tuple[float, str]:
    pauses = text_tools.internal_pauses(text)
    allowance = pauses * limits.pause_seconds
    note = f" + {pauses} pauses x {limits.pause_seconds:g}s" if pauses else ""
    if language in SYLLABLE_LANGUAGES:
        return text_tools.syllables(text, language) / limits.sps + allowance, f"{limits.sps:g} syllables/s{note}"
    return len(text_tools.words(text)) / (limits.wpm / 60) + allowance, f"{limits.wpm:.0f} wpm{note}"


def check_seconds(seconds: float, text: str | None, language: str | None, limits: Thresholds) -> dict:
    result: dict = {"value": round(seconds, 3)}
    if seconds < limits.min_seconds:
        return {**result, "status": "fail", "reason": f"{seconds:.2f}s < {limits.min_seconds}s (cut-off take)"}
    count = len(text_tools.words(text)) if text else 0
    if count <= 2:
        return {**result, "status": "pass", "words": count}
    expected, basis = expected_seconds(text or "", language, limits)
    low, high = expected * (1 - limits.duration_tolerance), expected * (1 + limits.duration_tolerance)
    result.update(words=count, expected=round(expected, 2), basis=basis, range=[round(low, 2), round(high, 2)])
    if not low <= seconds <= high:
        return {**result, "status": "fail", "reason": f"{seconds:.2f}s outside {low:.2f}-{high:.2f}s expected at {basis}"}
    return {**result, "status": "pass"}


def check_loudness(path: Path, samples, seconds: float, limits: Thresholds) -> dict:
    measured = audio.measure_loudness(path, seconds)
    clipped = audio.clipped_samples(samples)
    result = {"value": measured.lufs, "true_peak": measured.true_peak, "clipped": clipped}
    reasons = []
    if measured.true_peak is not None and measured.true_peak > limits.max_true_peak:
        reasons.append(f"true peak {measured.true_peak} dBTP > {limits.max_true_peak}")
    if clipped:
        reasons.append(f"{clipped} clipped samples")
    if reasons:
        return {**result, "status": "fail", "reason": "; ".join(reasons)}
    return {**result, "status": "pass"}


def check_take(path: Path, name: str, voice: str, text: str | None, language: str | None, limits: Thresholds) -> TakeReport:
    samples = audio.decode_mono(path, via_pipe=True)
    seconds = len(samples) / audio.ANALYSIS_RATE
    report = TakeReport(str(path), name, voice, text, language)
    report.checks["noise_floor_db"] = check_floor(samples, limits)
    report.checks["seconds"] = check_seconds(seconds, text, language, limits)
    report.checks["lufs"] = check_loudness(path, samples, seconds, limits)
    report.checks["quiet_at_source"] = quiet_check(report.checks["lufs"]["value"], None, limits, text)
    return report


SOFT_TAG = re.compile(r"soft|quiet|whisper|hush|gentl|murmur", re.IGNORECASE)


def quiet_check(lufs: float | None, voice_median: float | None, limits: Thresholds, text: str | None = None) -> dict:
    if lufs is None:
        return {"status": "fail", "value": None, "reason": "loudness not measurable (silent take)"}
    result: dict = {"value": lufs, "voice_median": voice_median}
    tagged = " (the line has a soft tag; listen before re-recording)" if text and any(SOFT_TAG.search(tag) for tag in text_tools.tags(text)) else ""
    if lufs < limits.quiet_lufs:
        return {**result, "status": "fail", "reason": f"quiet at source: {lufs} LUFS < {limits.quiet_lufs} (breathy read?){tagged}"}
    if voice_median is not None and voice_median - lufs > limits.quiet_delta:
        delta = round(voice_median - lufs, 1)
        return {**result, "status": "fail", "delta": delta, "reason": f"quiet at source: {delta} LU below the voice median{tagged}"}
    return {**result, "status": "pass"}


def apply_voice_medians(reports: list[TakeReport], limits: Thresholds) -> None:
    voices: dict[str, list[float]] = {}
    for report in reports:
        lufs = report.checks["lufs"]["value"]
        if lufs is not None:
            voices.setdefault(report.voice, []).append(lufs)
    for report in reports:
        values = voices.get(report.voice, [])
        median = round(statistics.median(values), 1) if len(values) >= 3 else None
        report.checks["quiet_at_source"] = quiet_check(report.checks["lufs"]["value"], median, limits, report.text)
