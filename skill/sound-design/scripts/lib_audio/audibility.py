"""SFX audibility: each cue's level against the voice and music it plays under, measured on the stems."""
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from . import dsp
from .cues_model import Sfx

WINDOW_BEFORE = 0.03
WINDOW_AFTER = 0.12
CLAMP_DB = 40.0


class CueLevel(BaseModel):
    at: float
    name: str
    role: str
    vs_bed_db: float


class AudibilityReport(BaseModel):
    event_cues: int
    texture_cues: int
    event_median_db: float | None
    quiet_events: list[CueLevel]
    passed: bool


def window_rms_db(signal: np.ndarray, rate: int, at: float) -> float:
    start = max(int((at - WINDOW_BEFORE) * rate), 0)
    end = max(int((at + WINDOW_AFTER) * rate), start + 1)
    return dsp.rms_db(signal[start:end])


def cue_name(cue: Sfx) -> str:
    return cue.kind or Path(cue.file or "").name


def cue_levels(cues: list[Sfx], sfx: np.ndarray, bed: np.ndarray, rate: int) -> list[CueLevel]:
    levels = []
    for cue in cues:
        difference = window_rms_db(sfx, rate, cue.at) - window_rms_db(bed, rate, cue.at)
        levels.append(CueLevel(at=round(cue.at, 3), name=cue_name(cue), role=cue.role, vs_bed_db=round(min(difference, CLAMP_DB), 1)))
    return levels


def assess(levels: list[CueLevel], median_floor_db: float, cue_floor_db: float) -> AudibilityReport:
    events = [level for level in levels if level.role == "event"]
    median = float(np.median([level.vs_bed_db for level in events])) if events else None
    return AudibilityReport(
        event_cues=len(events),
        texture_cues=len(levels) - len(events),
        event_median_db=round(median, 1) if median is not None else None,
        quiet_events=[level for level in events if level.vs_bed_db < cue_floor_db],
        passed=median is None or median >= median_floor_db,
    )


def describe(heard: AudibilityReport, cue_floor_db: float) -> list[str]:
    if heard.event_cues == 0:
        return ["warning: no event SFX; every animated event needs a sound or a logged reason for silence"]
    lines = [f"SFX audibility: {heard.event_cues} events, median {heard.event_median_db} dB vs voice+music; {heard.texture_cues} texture cues"]
    for level in heard.quiet_events:
        lines.append(f"warning: SFX {level.name} at {level.at}s sits {level.vs_bed_db} dB under voice+music (below {cue_floor_db}); raise its gain or mark it texture")
    return lines
