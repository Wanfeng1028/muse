# Sound for a launch film

Write `{projectDir}/audio/score.py`. Render it with:

```
python {skillDir}/audio/render.py {projectDir} {projectDir}/audio/score.py
```

Read `audio/synth.py` before choosing a voice. The timeline is `{projectDir}/public/timeline.json`. Cue names in the score must match it. A wrong name fails at load and names the missing cue.

## Rules

Do not use a stock riser, whoosh, impact, or pad. A filtered-noise sweep that also rises in pitch is a riser even if you synthesized it. `sub_swell` holds one low frequency. `inhale` is a breath that cuts. Neither rises. Do not add a voice that does.

Score the objects on screen. Under them, one chord, quiet enough that a keystroke still reads as a keystroke. Silence is a cue, not a gap to fill.

## One harmonic thread

`BED` maps each scene id to a chord. Change the chord only at a scene boundary. Share two or three tones with the previous scene, so the change is voice-leading rather than a new piece of music. An empty list is silence. Use it for a scene with no bed.

To resolve a chord inside a scene, set `BED_SPLIT = {"S7": "fallaway[0]"}` and provide both `"S7"` and `"S7+"`. That is the only mid-scene change, and it belongs on a cue.

Notes are `"D3"`, `"F#4"`, `"Bb4"`. A weighted partial is `(50, 0.55)`, MIDI number first. Four or five notes is enough. A scene with no new picture gets the same chord, not a thicker one.

## Hits mean something

A run of the same voice states a chord. Five wooden bars, D E F# A B, say "these five are the same kind of thing." Five glass pings, D F# A C# E, say "these five complete a chord." Pick the notes on purpose. Do not pick random pitches, and do not use the same pitch for everything.

One logo tone returns. In the Droid film it is an FM bell on D3 at ratio 1.4. It plays when the mark appears, once under a caption, and once at the end. Three times is a callback. Ten times is a sting.

Leave a cue silent when the viewer is reading a sentence. An event you omit is silent, and the report will not list it. Add the event only when you want the report to show that the omission was a choice.

## Map the picture

| What happens on screen | Voice | Bus |
|---|---|---|
| A key, on paper | `keystroke(kind="paper")` | room, quiet |
| A key, in a terminal | `keystroke(kind="terminal")` | room, drier and tighter pan |
| The submit key | `keystroke(kind="enter")` | room |
| An object lands | `modal_bar(note)` | room |
| The same land, but glass or metal | `glass_drop(note)` or `glass_ping(note)` | plate |
| A row of small things fans out | `pluck(note)`, 35 ms apart, panned left to right | room |
| A card settles | `felt_thump(note)` | room |
| A lock, a check, a merge | `latch_click()` | room, dry |
| A page turns | `paper_turn(dur)` | room |
| Paper tears | `paper_tear()` | room |
| A receipt prints | `printer_burst(dur, rate)` | room |
| A stamp comes down | `stamp()` | room |
| Blades or a rotor speed up | `air_spin(dur, start_hz, end_hz)` | dry |
| A frame goes black on a shutter | `shutter()` | room |
| A meter fills | `clock_run(dur, rate0, rate1, pitch, pan)` | dry |
| A value climbs and wins | `glide(f0, f1, dur)` then `fifth(note)` | plate |
| A scene opens | `tone(note)` at about -24 dB, or nothing | plate |
| The bed needs weight | `sub_swell(dur)`, one steady frequency | dry |
| A zoom into black | `inhale(dur)`, cut at the black frame | room |

A headline gets a tone at -24 dB, or nothing. It does not get a whoosh. If the cut is already clear from the picture, use nothing.

`bus` is `dry`, `room`, or `plate`. Room is short and for foley. Plate is for bells and glass. A keystroke on the plate sounds like a trailer. A bell with no plate sounds like a beep.

## Write the score

```python
from synth import fm_bell, keystroke, modal_bar

SEED = 7  # one generator for the whole score; the render is deterministic

BED = {
    "S1": [("D3", 0.5), ("A3", 0.4), ("F4", 0.3)],
    "S2": [],
}

# (scene, cue, voice, kwargs, bus, gain_db, pan, delay_s)
EVENTS = [
    ("S1", "headline", modal_bar, {"note": "D4"}, "room", -10, -0.3, 0.0),
    ("S1", "mark", modal_bar, {"note": "A4"}, "room", -10, 0.2, 0.0),
    ("S2", "meterFull", fm_bell, {"note": "D3", "ratio": 1.4}, "plate", -14, 0.0, 0.0),
    ("S2", "meterFull", keystroke, {"kind": "enter"}, "room", -8, 0.0, 0.0),
]

SILENCE = [
    ("S1", "headline", "mark"),
]
```

Fields after `voice` are optional. The defaults are `{}`, `dry`, 0 dB, pan 0, and delay 0.

`cue` is a name, `chips[2]` for one frame of a list, or an int scene-local frame when the picture has no cue there. The shutter in the Droid film lands 40 frames after `rotorSpin`, so the score uses `172`. Prefer a cue name. An int hides the sync from the next person.

`delay_s` is for a strum on one cue, or for a tail that must crest on the cue. `swell_in` ends on its last sample, so set `delay_s` to `-0.9` for a 0.9 s swell. Two voices on one cue with no delay play together. That is the click under the bell.

Gains are dB, relative to each other. The loudness pass sets the final level. Keep foley around -14 to -8, the logo around -12, and an entrance tone around -24. Leave the bed at its default of -28 dBFS before that pass. If one hit is louder than the scene, lower that hit. Do not raise the rest to match it.

Pan runs from -1 to 1. Keep a single centered object inside ±0.15. Pan a row to match the row. A centered headline in wide stereo sounds like a trailer.

## Silence

`SILENCE` entries are `(scene, start_cue, end_cue)` in one scene, or a pair of points when the window crosses a scene. A point is `(scene, cue)` or `(scene, cue, frame_offset)`.

The offset is only for letting a short hit finish. The meter clack is 40 ms, so the window opens two frames after `meterFull`, not on the cue itself. Opening on the cue deletes the hit.

After loudnorm the renderer writes those samples back to digital zero. A fade of 20 ms into the window keeps the cut from ticking. The window itself is exact zero, on every bus, including reverb tails.

One window, or two. A silence in every scene reads as a dropout, not as restraint.

## Verify

Render, then check the file the renderer wrote, not the raw mix.

```
ffprobe -hide_banner -v error -show_entries format=duration:stream=sample_rate,channels,codec_name {projectDir}/public/score.wav
ffmpeg -hide_banner -nostats -i {projectDir}/public/score.wav -af ebur128=peak=true -f null -
```

Duration is `total / fps` from the timeline, to the millisecond, 48 kHz, stereo, pcm_s24le. Integrated loudness within about 0.5 LU of -14. True peak at or below -1 dBFS. `{projectDir}/audio/cues_report.txt` prints one line per event with an absolute time, and `maxabs=0.000e+00` for every silence window.

If true peak fails, the cause is usually a transient with energy above 10 kHz, or a buffer edge that is not zero. `declick` handles the edge. Band-limit the transient. Do not add a limiter in the score. The loudnorm pass is linear on purpose, so a window of zeros survives it.

If a cue is missing from the report, it was not in `EVENTS`. The renderer does not invent events for cues you skipped.

## The Droid film, as a reference

`audio/scores/droid_launch.py` is one score built this way. S1 is dry. S2 through S6 each hold one chord. S5 cuts to silence on the full meter and stays there until the page turns. S7 resolves at the fall. S8 is two Ds. The logo bell is D3 at ratio 1.4, and it returns under the caption and after the tear. Copy the shape. Do not copy the cue list into a film that does not have those cues.
