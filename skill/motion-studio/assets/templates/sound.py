"""Soundtrack for {{TITLE}}: `studio.py mix <film>` runs this and writes out/mix.wav.

Every cue sits on the film's grid (m.b(bar, beat), read from film.html's K.setup), and every sound is recorded
or licensed (library assets by id). Pick the music first, set the film's bpm to the track's measured bpm, then
place cues where the picture has events.
"""
from pathlib import Path

import audio as A    # vendored into this folder by `studio.py new`, like kit.js: the film never depends on the plugin's path

m = A.Mix(Path(__file__).parent)
b = m.b

# ── music: song bars (corrected) played back to back from film bar 0 ──
# m.music("mixkit-371", [(7, 9), (15, 19)], at_bar=0, gain=0.8)

# ── ambience beds: (from_s, to_s, level) ──
# m.bed("mixkit-1213", [(b(2), b(6), 1.0)], gain=0.5)

# ── one-shots on the beat: measured peaks land exactly on the cue ──
# click = A.asset("mixkit-1113")
# for k in range(4):
#     m.put(click, b(0, k), 0.5)

# steps = A.single_hits("mixkit-1230", "mixkit-1214")   # footsteps cut from longer recordings
# thud = A.asset("impactSoft_heavy_003")               # Kenney CC0 impact pack

m.master()
