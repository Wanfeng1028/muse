"""Score for the template's three demo scenes. Cue names match src/timeline.ts."""

from synth import clack, fm_bell, glass_ping, keystroke, latch_click, modal_bar, tone

SEED = 7

BED = {
    "S1": [("D3", 0.5), ("A3", 0.4), ("F4", 0.32), ("A4", 0.22)],
    "S2": [("F3", 0.46), ("A3", 0.4), ("C4", 0.34), ("E4", 0.26)],
    "S3": [("D4", 0.4), ("D5", 0.22)],
}

EVENTS = [
    ("S1", "mark", fm_bell, {"note": "D3", "ratio": 1.4, "dur": 2.2}, "plate", -12, 0.0),
    ("S1", "headline", tone, {"note": "D4", "dur": 1.0}, "plate", -22, 0.0),
    ("S1", "wipe", keystroke, {"kind": "paper"}, "room", -14, 0.0),
    ("S1", "meter", latch_click, {}, "room", -12, 0.0),
    ("S2", "chips[0]", modal_bar, {"note": "D4"}, "room", -10, -0.3),
    ("S2", "chips[1]", modal_bar, {"note": "F4"}, "room", -10, 0.0),
    ("S2", "chips[2]", modal_bar, {"note": "A4"}, "room", -10, 0.3),
    ("S2", "complete", clack, {}, "dry", -8, 0.0),
    ("S2", "merge", glass_ping, {"note": "D5", "dur": 1.4}, "plate", -16, 0.0),
    ("S3", "lockup", latch_click, {}, "room", -8, 0.0),
    ("S3", "lockup", fm_bell, {"note": "D3", "ratio": 1.4, "dur": 2.4}, "plate", -14, 0.0),
    ("S3", "url", keystroke, {"kind": "paper"}, "room", -14, 0.0),
]

SILENCE = []
