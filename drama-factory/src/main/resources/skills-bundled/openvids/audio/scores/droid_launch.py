"""Score for the 75s Droid launch film.

Cue names match examples/droid-launch/public/timeline.json. The bed changes
only at scene boundaries, except S7, which resolves when the cards fall.
One silence window, from just after the meter clack to the page turn.
"""

from synth import (
    air_spin, clack, clock_run, detent, felt_thump, fifth, fm_bell, friction,
    glass_drop, glass_ping, glide, granular, inhale, keystroke, latch_click,
    modal_bar, note_hz, opening, paper_slide, paper_tear, paper_turn, pen_tick,
    pluck, printer_burst, rest, shutter, stamp, sub_swell, swell_in, thud, tone,
)

SEED = 20261004

# Voice-led. Adjacent scenes share tones. S1 is dry. S7 splits at fallaway.
BED = {
    "S1": [],
    "S2": [(50, 0.55), (57, 0.42), (65, 0.38), (69, 0.30), (72, 0.22)],
    "S3": [(46, 0.50), (58, 0.40), (65, 0.36), (69, 0.32), (70, 0.22)],
    "S4": [(45, 0.42), (57, 0.48), (64, 0.36), (69, 0.30), (72, 0.20)],
    "S5": [(43, 0.40), (55, 0.46), (62, 0.38), (67, 0.28), (74, 0.16)],
    "S6": [(52, 0.38), (57, 0.34), (64, 0.42), (66, 0.36), (71, 0.30), (76, 0.22)],
    "S7": [(43, 0.36), (55, 0.40), (60, 0.28), (65, 0.32), (67, 0.22)],
    "S7+": [(50, 0.42), (57, 0.40), (62, 0.34), (66, 0.28), (69, 0.18)],
    "S8": [(74, 0.55), (86, 0.28)],
}
BED_SPLIT = {"S7": "fallaway[0]"}

LOGO = {"note": "D3", "ratio": 1.4}

# S3 race is raceWin - raceStart = 110 frames at 30 fps.
RACE = 110 / 30
# S5 meters fill from frame 120 to 228.
FILL = (228 - 120) / 30
# S1 blades run from rotorSpin to 40 frames later, when the frame is black.
SPIN = 40 / 30
# S7 inhale runs from zoom to the black frame at 230. 230 is picture, not a cue.
BREATH = (230 - 196) / 30

CHIP = ["D4", "E4", "F#4", "A4", "B4"]
CHECKS = ["D5", "F#5", "A5", "C#6", "E6"]
POURS = ["D4", "E4", "F#4", "A4", "B4", "D5", "E5", "F#5"]
FALL = ["A4", "F#4", "D4"]


def E(scene, cue, fn, kwargs=None, bus="dry", gain_db=0.0, pan=0.0, delay=0.0):
    return (scene, cue, fn, kwargs or {}, bus, gain_db, pan, delay)


EVENTS = []

# S1. Cream, dry, close. Five paper keys, enter, the logo, then blades.
for i in range(5):
    EVENTS.append(E("S1", f"keystrokes[{i}]", keystroke, {"kind": "paper"}, "room", -8.5, 0.0))
EVENTS += [
    E("S1", "enter", keystroke, {"kind": "enter"}, "room", -6.5, 0.0),
    E("S1", "rotorForm", detent, {}, "room", -8.0, 0.0),
    E("S1", "rotorForm", fm_bell, {**LOGO, "dur": 2.6, "index": 2.2, "tau": 1.15}, "plate", -11.0, 0.0, 0.02),
    E("S1", "rotorSpin", air_spin, {"dur": SPIN, "start_hz": 4.0, "end_hz": 40.0}, "dry", -8.0, 0.0),
    E("S1", 172, shutter, {}, "room", -6.0, 0.0),
]

# S2. Headline is a tone, not a whoosh. Chips land as a pentatonic run.
EVENTS.append(E("S2", "headline", tone, {"note": "A3", "dur": 1.4, "index": 0.8, "tau": 0.7}, "plate", -24.0, 0.0))
for i, note in enumerate(CHIP):
    pan = -0.35 + 0.7 * (i / 4)
    EVENTS.append(E("S2", f"chipLand[{i}]", friction, {"dur": 0.18}, "dry", -29.0, pan, -0.14))
    EVENTS.append(E("S2", f"chipLand[{i}]", modal_bar, {"note": note, "dur": 0.6}, "room", -10.0, pan))
for i in range(5):
    EVENTS.append(E("S2", "lanes", pen_tick, {"pitch": 1600 + i * 180}, "room", -20.0,
                    -0.4 + i * 0.2, i * 0.045))

# S3. Three tick streams plus a fifth glide. The win is a chord, then a latch.
EVENTS.append(E("S3", "headline", tone, {"note": "Bb4", "dur": 1.2, "index": 0.6, "tau": 0.55}, "plate", -25.0, 0.0))
for pan, r0, r1 in ((-0.45, 3.5, 14.0), (0.15, 2.5, 9.0), (0.5, 2.0, 7.0)):
    EVENTS.append(E("S3", "raceStart", granular, {
        "dur": RACE, "rate0": r0, "rate1": r1, "pan": pan, "gain": 0.5,
    }, "dry", -23.0, 0.0))
EVENTS += [
    E("S3", "raceStart", glide, {"f0": "D4", "f1": "A4", "dur": RACE, "tau_tail": 0.5}, "plate", -18.0, 0.05),
    E("S3", "raceWin", fifth, {"note": "D4", "dur": 1.5}, "plate", -15.0, 0.0),
    E("S3", "raceWin", latch_click, {}, "room", -7.0, 0.02),
    E("S3", "growToTerminal", opening, {"dur": 0.42}, "room", -16.0, 0.0),
]

# S4. Tighter keys. specOk states D5. The fan is the same pentatonic, up an octave.
for i in range(12):
    EVENTS.append(E("S4", f"keystrokes[{i}]", keystroke, {"kind": "terminal"}, "room", -12.0, 0.0))
EVENTS += [
    E("S4", "specOk", glass_ping, {"note": "D5", "dur": 1.1}, "plate", -13.0, 0.0),
    E("S4", "specOk", latch_click, {}, "room", -13.0, 0.0),
]
for i, note in enumerate(CHIP):
    EVENTS.append(E("S4", "fanOut", pluck, {"note": note_hz(note) * 2, "dur": 0.5, "brightness": 0.45},
                    "room", -12.0, -0.6 + 1.2 * (i / 4), i * 0.035))
for i, note in enumerate(CHECKS):
    EVENTS.append(E("S4", f"checks[{i}]", glass_ping, {"note": note, "dur": 2.6},
                    "plate", -14.0, -0.4 + 0.8 * (i / 4)))
EVENTS += [
    E("S4", "merge", swell_in, {"notes": CHECKS, "dur": 0.9}, "plate", -12.0, 0.0, -0.9),
    E("S4", "merge", thud, {}, "room", -7.0, 0.0),
]

# S5. Felt cards climb G A D. Three clocks fill, a dry clack, then silence.
for i, note in enumerate(["G4", "A4", "D5"]):
    EVENTS.append(E("S5", f"cards[{i}]", felt_thump, {"note": note, "dur": 0.8},
                    "room", -11.0, -0.3 + 0.3 * i))
for name, r0, r1, pan, pitch in (
    ("5h", 2.0, 11.0, 0.22, 2100.0),
    ("7d", 1.2, 7.5, -0.28, 1600.0),
    ("30d", 0.7, 4.5, 0.0, 1100.0),
):
    EVENTS.append(E("S5", "meterFill", clock_run, {
        "dur": FILL, "rate0": r0, "rate1": r1, "pitch": pitch, "pan": pan,
        "gain0": 0.35, "gain1": 0.7,
    }, "dry", -22.0, 0.0))
EVENTS += [
    E("S5", "meterFull", clack, {}, "dry", -10.0, 0.0),
    E("S5", "pageFlip", paper_turn, {"dur": 0.62}, "room", -8.0, 0.04),
]

# S6. A sub, not a riser. Pours alternate wood and glass. The logo returns twice.
EVENTS += [
    E("S6", "coreRise", sub_swell, {"dur": 2.4, "f": 46.0}, "dry", -9.0, 0.0),
    E("S6", "coreRise", glide, {"f0": "D3", "f1": "E3", "dur": 1.6, "tau_tail": 0.8}, "plate", -22.0, 0.0, 0.15),
]
for i, note in enumerate(POURS):
    glass = i % 2 == 1
    fn = glass_drop if glass else modal_bar
    kwargs = {"note": note, "dur": 0.38} if glass else {"note": note, "dur": 0.32, "strike": 0.7}
    EVENTS.append(E("S6", f"modelsPour[{i}]", fn, kwargs,
                    "plate" if glass else "room", -14.0, 0.45 if glass else -0.45))
EVENTS += [
    E("S6", "caption", fm_bell, {**LOGO, "dur": 1.8, "index": 1.2, "tau": 0.9}, "plate", -22.0, 0.0),
    E("S6", "merge", latch_click, {}, "room", -9.5, -0.15),
    E("S6", "merge", latch_click, {}, "room", -9.5, 0.15, 0.07),
    E("S6", "merge", fm_bell, {**LOGO, "dur": 2.2, "index": 2.0, "tau": 1.0}, "plate", -12.5, 0.0, 0.04),
]

# S7. One key. The second line is read, not scored. Cards fall. Breath cuts at black.
EVENTS += [
    E("S7", "line1", keystroke, {"kind": "paper"}, "room", -13.0, 0.0),
    E("S7", "line2", rest, {}, "dry", 0.0, 0.0),
]
for i, note in enumerate(FALL):
    pan = -0.3 + 0.3 * i
    EVENTS.append(E("S7", f"fallaway[{i}]", modal_bar, {"note": note, "dur": 0.42, "strike": 0.65},
                    "room", -12.5, pan))
    EVENTS.append(E("S7", f"fallaway[{i}]", paper_slide, {"dur": 0.32}, "room", -18.0, pan * 0.5, 0.02))
EVENTS.append(E("S7", "zoom", inhale, {"dur": BREATH}, "room", -13.0, 0.0))

# S8. Stepper, stamp, tear, and the logo ringing out under a second.
EVENTS.append(E("S8", "printStart", printer_burst, {"dur": 0.16, "rate": 36.0}, "room", -11.0, 0.0))
for i, rate in enumerate((47, 51, 54, 51, 46, 57)):
    EVENTS.append(E("S8", f"printLines[{i}]", printer_burst, {"dur": 0.12, "rate": float(rate)},
                    "room", -10.0, 0.0))
EVENTS += [
    E("S8", "stamp", stamp, {}, "room", -5.0, 0.0),
    E("S8", "tear", paper_tear, {"dur": 0.35}, "room", -8.5, 0.05),
    E("S8", "tear", fm_bell, {**LOGO, "dur": 1.05, "index": 1.8, "tau": 0.42}, "plate", -14.0, 0.0, 0.28),
]

# meterFull's clack is ~40 ms. Zero after it, through to the page.
SILENCE = [
    (("S5", "meterFull", 2), ("S5", "pageFlip")),
]
