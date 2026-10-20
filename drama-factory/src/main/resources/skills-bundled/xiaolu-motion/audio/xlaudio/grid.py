"""卡点工具: beat grid, bar/beat <-> seconds <-> video frames.

``BeatGrid`` is a constant-tempo grid (our own synthesized music, or any
track whose tempo is known). ``BeatMap`` holds an explicit list of beat times
(e.g. Jianying's cached beat analysis, see ``load_jianying_beat``) and offers
the same lookups. Indices are 0-based in code (bar 0 = first bar); ``bbt()``
takes DAW-style 1-based "bar.beat" positions.
"""
import json
import math

import numpy as np


def frame_of(t, fps=30.0):
    """seconds -> nearest video frame index."""
    return int(round(t * fps))


def frame_time(frame, fps=30.0):
    return frame / fps


def frame_locked_bpms(fps=30.0, lo=60.0, hi=180.0):
    """tempos whose beat lands exactly on a whole number of frames (60*fps/k)."""
    out = []
    k = 1
    while True:
        bpm = 60.0 * fps / k
        if bpm < lo:
            break
        if bpm <= hi:
            out.append(dict(bpm=round(bpm, 4), frames_per_beat=k))
        k += 1
    return out


class BeatGrid:
    def __init__(self, bpm, beats_per_bar=4, offset=0.0, fps=30.0):
        self.bpm = float(bpm)
        self.bpb = int(beats_per_bar)
        self.offset = float(offset)
        self.fps = float(fps)
        self.beat_s = 60.0 / self.bpm
        self.bar_s = self.beat_s * self.bpb

    # --- positions -> seconds -------------------------------------------------
    def beat_time(self, beat):
        """0-based beat index (float ok) -> seconds."""
        return self.offset + beat * self.beat_s

    def bar_time(self, bar, beat=0.0):
        """0-based bar (+ 0-based beat inside the bar) -> seconds."""
        return self.offset + (bar * self.bpb + beat) * self.beat_s

    def bbt(self, bar1, beat1=1.0):
        """DAW-style 1-based position: bbt(5, 1) = downbeat of the 5th bar."""
        return self.bar_time(bar1 - 1, beat1 - 1)

    # --- seconds -> positions -------------------------------------------------
    def bar_beat(self, t):
        """seconds -> (bar, beat_in_bar) 0-based, beat is fractional."""
        b = (t - self.offset) / self.beat_s
        bar = math.floor(b / self.bpb + 1e-9)
        return bar, b - bar * self.bpb

    def snap(self, t, division=1.0, mode='nearest'):
        """snap seconds to the grid; division in beats (1 beat, 0.5 8th, 0.25 16th,
        beats_per_bar = bar)."""
        q = (t - self.offset) / (self.beat_s * division)
        k = {'nearest': round, 'floor': math.floor, 'ceil': math.ceil}[mode](q + (0 if mode == 'nearest' else 0))
        return self.offset + k * self.beat_s * division

    # --- lists ------------------------------------------------------------------
    def beats(self, t0, t1, division=1.0):
        step = self.beat_s * division
        k0 = math.ceil((t0 - self.offset) / step - 1e-9)
        k1 = math.floor((t1 - self.offset) / step + 1e-9)
        return [self.offset + k * step for k in range(k0, k1 + 1)]

    def downbeats(self, t0, t1):
        return self.beats(t0, t1, self.bpb)

    def frame(self, t):
        return frame_of(t, self.fps)

    def frame_error_ms(self):
        """largest quantisation error (ms) between a beat and its nearest frame over 64 bars."""
        ts = np.array(self.beats(self.offset, self.offset + 64 * self.bar_s))
        return float(np.max(np.abs(np.round(ts * self.fps) / self.fps - ts)) * 1000.0)

    def table(self, t_end, division=1.0, t_start=0.0):
        """rows for storyboards: bar, beat (1-based), seconds, frame, downbeat flag."""
        rows = []
        for t in self.beats(max(t_start, self.offset), t_end, division):
            bar, beat = self.bar_beat(t)
            rows.append(dict(bar=bar + 1, beat=round(beat + 1, 4), t=round(t, 6), frame=self.frame(t),
                             frame_err_ms=round((self.frame(t) / self.fps - t) * 1000.0, 3),
                             downbeat=abs(beat) < 1e-6))
        return rows

    def to_dict(self, t_end):
        return dict(bpm=self.bpm, beats_per_bar=self.bpb, offset=self.offset, fps=self.fps, beat_s=self.beat_s,
                    bar_s=self.bar_s, frame_error_ms=self.frame_error_ms(),
                    beats=self.table(t_end))


class BeatMap:
    """explicit beat list (times in seconds, positions 1..beats_per_bar)."""

    def __init__(self, times, positions=None, fps=30.0, source=None):
        self.times = np.asarray(times, dtype=float)
        self.pos = np.asarray(positions if positions is not None else np.ones(len(times)), dtype=int)
        self.fps = float(fps)
        self.source = source

    def tempo(self):
        d = np.diff(self.times)
        return float(60.0 / np.median(d)) if len(d) else float('nan')

    def beats(self, t0, t1):
        return [float(t) for t in self.times[(self.times >= t0) & (self.times <= t1)]]

    def downbeats(self, t0, t1):
        m = (self.times >= t0) & (self.times <= t1) & (self.pos == 1)
        return [float(t) for t in self.times[m]]

    def snap(self, t, downbeat=False):
        ts = self.times[self.pos == 1] if downbeat else self.times
        return float(ts[np.argmin(np.abs(ts - t))])

    def table(self):
        return [dict(beat=int(p), t=round(float(t), 6), frame=frame_of(t, self.fps), downbeat=bool(p == 1))
                for t, p in zip(self.times, self.pos)]


def load_jianying_beat(path, fps=30.0):
    """Jianying (and some other editors) can export a beat-analysis sidecar
    file for a track as JSON, shaped like this:
    {"time": [ms...], "value": [1,2,3,4,1,...], "energy": [...]}."""
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    return BeatMap(np.asarray(d['time'], float) / 1000.0, d.get('value'), fps=fps, source=str(path))
