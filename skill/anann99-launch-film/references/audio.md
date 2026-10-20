# Audio: composing, mastering and verifying the score

The default is an **original score composed to the edit**. Every cut, word pop, click and number landing has a sound event at the exact sample. That sync is most of what makes a music-only launch film feel expensive.

The alternative is a licensed track the user provides (see the end of this file).

## 1. Grid and form
- **Tempo:** pick the tempo first. 120 BPM is the default; at 30 fps a beat is exactly 15 frames and a bar is 2 s. Make the storyboard's section changes land on bar lines.
- **Form for a 60 s film:**

  | Time | Section | Content |
  |---|---|---|
  | 0–12 | Intro | dark pad, soft sub "heartbeat" on bar downbeats, clock ticks on 8ths, a pluck motif; riser from 10.0 into **real silence** 11.75–12.0 |
  | 12.0 | Drop | impact + reverse cymbal ending exactly on the downbeat + logo sting; full groove starts (kick 4/4, clap 2&4, offbeat hats, sidechained sub-bass and pad) |
  | 12–28 | Groove A | one chord per bar (e.g. Am–F–C–G) |
  | 28–42 | Groove B | adds 16th hats, octave arp, a sparse bell motif that rests where sound-design hits need space |
  | 42–52 | Proof | groove continues; impacts on the number landings; riser and snare fill into the close |
  | 52–60 | Close | drums out on the downbeat; warm major pad, bell arpeggio; final logo sting chord + boom + shimmer with a long tail; fade over the last 0.5 s |

- **Pan with the picture:** cards fanning right pan right, bars rising left-to-right pan across.

## 2. `audio/score.json` (drives `compose.py`)
```json
{
  "duration": 60.0,
  "bpm": 120,
  "out": "video/public/audio/score.wav",
  "sections": [
    {"start": 0, "end": 12, "energy": "intro", "chords": ["Am9"]},
    {"start": 12, "end": 28, "energy": "groove", "chords": ["Am", "F", "C", "G"]},
    {"start": 28, "end": 42, "energy": "peak", "chords": ["Am", "F", "C", "G"]},
    {"start": 42, "end": 52, "energy": "peak", "chords": ["Am", "F", "C", "G"]},
    {"start": 52, "end": 60, "energy": "outro", "chords": ["C", "Fmaj7"]}
  ],
  "silence": [[11.75, 12.0]],
  "hits": [
    {"t": 1.0, "kind": "tick", "note": "pill swap"},
    {"t": 12.0, "kind": "drop", "note": "logo"},
    {"t": 40.5, "kind": "click", "note": "Accept"},
    {"t": 56.0, "kind": "logo-sting", "note": "end card"}
  ]
}
```
- **Hit kinds** map to instruments in `compose.py`: `tick`, `soft-tick`, `tick-rise`, `type-hit`, `swish`, `whoosh`, `click`, `stamp`, `thunk`, `bell`, `impact`, `drop`, `logo-sting`, `riser-start`, `snare-fill`.
- **Structural kinds** are informational: `section`, `drums-out`, `silence`, `fade`.

## 3. Mastering targets
- Integrated loudness **−14 LUFS** (±0.5), the streaming/social norm. True peak **≤ −1.0 dBTP** (4× oversampled check).
- Mono below ~140 Hz; DC removed; high-pass at ~25 Hz.
- Glue compression (low ratio), then a look-ahead limiter. Iterate make-up gain until both targets hold.
- Exact length: `round(duration × 48000)` samples. Short fades on every one-shot (no clicks).

## 4. Verification (`compose.py` prints all of this)
- LUFS, sample peak, true peak, DC offset, and per-section loudness. The drop must be clearly the loudest moment of Act I.
- **Placement error** of every hit: 0.00 ms by construction.
- **Detected onset error** of every hit (spectral-flux onset detector). A soft tick inside a dense groove can read as a 20–40 ms "miss" because of masking. If placement is 0.00, that's fine.
- `audio/score_viz.png`: waveform, spectrogram, momentary loudness, and hit markers. **Look at it**: sections should be visible as blocks, and silences should be truly empty.

## 5. Tonal balance: the step most synth scores miss
Raw synth mixes come out **too bright (1–10 kHz) and too thin in the low mids (80–320 Hz)** compared with professionally produced music. Fix by measurement:
```bash
.venv/bin/python <skill>/scripts/band-match.py reference.wav video/public/audio/score.wav --ref-range 20 100 --ours-range 12 52
```
- The script prints per-octave energy (relative dB) for both files and the difference, and suggests shelf/peak moves.
- Add them to the master chain in `compose.py`, then re-run until every groove band is within ~±4 dB.
- A typical correction is +3.5 dB low shelf at 320 Hz, +4 dB peak at 230 Hz, and −5.5 dB high shelf at 1.4 kHz.
- Good references: the user's existing video's music bed, or any professionally mixed track in a similar genre.

**Always tell the user** that the score was verified by analysis, not by ears, and that they should listen on speakers and a laptop before release.

## 6. Licensed track instead
- Get the file and licence from the user. Trim or loop it to the film length at bar boundaries.
- Measure its tempo: use beat-tracking, or ask for the BPM. Retime `scenes.json` boundaries to its bar lines. Keep the drop on its biggest downbeat.
- Optionally layer sound-design hits from `synth.py` (ticks, clicks, whooshes, impacts) at a low level, with `compose.py` in "sfx-only" mode (`"music": false` in `score.json`). Then mix the two with ffmpeg `amix` and re-master to −14 LUFS.
- Put the licence note in the project README.
