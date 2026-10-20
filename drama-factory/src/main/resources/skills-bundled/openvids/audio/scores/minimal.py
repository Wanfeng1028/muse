"""A 3-scene launch score. One chord per scene, foley on the cues, one silence.

Scene ids and cue names match audio/fixtures/timeline.json.
"""

from synth import (
    clack, fm_bell, glass_ping, keystroke, latch_click, modal_bar, tone,
)

SEED = 7

# D minor, then its relative major, then the logo tone alone.
BED = {
    "S1": [("D3", 0.5), ("A3", 0.4), ("F4", 0.32), ("A4", 0.22)],
    "S2": [("F3", 0.46), ("A3", 0.4), ("C4", 0.34), ("E4", 0.26)],
    "S3": [("D4", 0.4), ("D5", 0.22)],
}

# (scene, cue, voice, kwargs, bus, gain_db, pan)
EVENTS = [
    ("S1", "headline", tone, {"note": "D4", "dur": 1.0}, "plate", -22, 0.0),
    ("S1", "mark", fm_bell, {"note": "D3", "ratio": 1.4, "dur": 2.2}, "plate", -12, 0.0),
    ("S2", "chips[0]", modal_bar, {"note": "D4"}, "room", -10, -0.4),
    ("S2", "chips[1]", modal_bar, {"note": "F4"}, "room", -10, -0.2),
    ("S2", "chips[2]", modal_bar, {"note": "A4"}, "room", -10, 0.0),
    ("S2", "chips[3]", modal_bar, {"note": "C5"}, "room", -10, 0.2),
    ("S2", "chips[4]", modal_bar, {"note": "D5"}, "room", -10, 0.4),
    ("S2", "meterFull", clack, {}, "dry", -8, 0.0),
    ("S3", "lockup", latch_click, {}, "room", -8, 0.0),
    ("S3", "lockup", fm_bell, {"note": "D3", "ratio": 1.4, "dur": 2.4}, "plate", -14, 0.0),
    ("S3", "url", keystroke, {"kind": "paper"}, "room", -14, 0.0),
    ("S3", "url", glass_ping, {"note": "D5", "dur": 1.4}, "plate", -16, 0.0),
]

# The clack at meterFull is 40 ms. Zero from two frames after it to the lockup.
SILENCE = [
    (("S2", "meterFull", 2), ("S3", "lockup")),
]
