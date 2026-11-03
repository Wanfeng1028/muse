# SFX and foley

Placing, choosing and synthesising sound effects.

Contents
1. SFX and foley

---

## SFX and foley

- **Every animated event gets a sound**, or a logged reason for its silence in the decision log. Hits get a whoosh,
  slap or thump; transitions get riser-in and hit-on-cut; counters and timers get ticks; UI gets a click on the press
  frame, a key per typed character (same rhythm as the typing animation), pops at a cascade's own stagger, a sparkle on
  a real state change. Celebration sounds only for real events. Silence is a decision, never a default.
- **Calibration (the Repitis launch film, the reference this suite was built from)**: 168 cues in 73 s, about 2.3 per
  second; event sounds sat at a median of −8 dB against voice plus music, tick runs around −30 dB as texture. A film
  that came out flat measured 17 cues in 34 s at a median of −25 dB: present in the cue sheet, inaudible in the mix.
- **Place by the transient**, not the file start: align the measured peak (argmax |s|) to the visual contact frame,
  which usually means the file starts a few frames early. Without a peak measurement, lead by 2 to 3 frames. Early feels
  synced; late feels broken. In Remotion: `<Sequence from={eventFrame − Math.round(peakMs / 1000 * fps)}>`.
- Gains (`mix.py` peak-normalises each SFX to −10.5 dBFS, then multiplies by the cue's `gain`): 0.3 to 0.6 for most
  events (Repitis median 0.45), 0.8 to 1.0 for hero hits (the drop, the logo, the price), 0.15 to 0.3 only for runs
  marked `"role": "texture"` (tick runs, typing keys). Calm films use softer timbres, not lower gains: a
  sound under the bed is not soft, it is missing.
- **Audibility is measured, because you can't hear.** `mix.py` compares each event cue with the voice and music under
  it and fails when the event median sits more than 12 dB under (`--sfx-median-db`); it warns for each event more than
  20 dB under. Fix by raising gains, never by marking events as texture.
- No assets is no excuse for silence: `scripts/foley.py` synthesises a deterministic kit (pop, blip, thump, slap, stamp,
  whoosh, swell, tear, tick, key, flip, pluck, chime, riser, bass hit, shimmer, reverse swoosh), tunable to the key.
- Sources: Mixkit, Pixabay, freesound (check each CC licence; CC-BY needs attribution), ElevenLabs SFX (≤ 22 s).
  Never the meme sounds in the official `remotion.media` list (vine boom, bruh, wilhelm) in brand films.
- The offer or price moment is the loudest moment of the film.
- Choose sounds by film genre, not by event. Product films: whoosh (camera), impact (landing), riser (build), sparkle
  (light), with a strong-kick bed. **Tuned foley is the signature**: pops and plucks pitched to the song's key and
  stepping up a scale across a cascade (0, 2, 5, 7, 12…) make reveals feel composed; `foley.py --key` renders them. What is
  banned is stock game-pack samples (cartoon boings, notification bleeps, arcade coins), not pitched synthesis. A real
  click or switch on screen gets its real foley. A signature phrase: riser, impact ~35 f later at the loudness peak,
  sparkle ~25 f after that.
- Density follows the animation: playful or energetic films land near Repitis (2.3 cues per second); calm films have
  fewer animated events and so fewer cues, but every event is still covered. Under narration, put hits in the pauses between sentences
  (gaps ≥ 0.3 s) or on the naming word; textures can run under speech. Transitions get only the build, not the
  landing. No closing ding.
- Repeated pops step down in level (0.40 → 0.25), alternate two samples, and tighten with the animation; when they get too
  dense, let them blur into one swoosh.
- Remotion `volume` multiplies the file's own level: an SFX peaking at −24.6 dB stays inaudible under a bed even at 1.0.
  `volume > 1` amplifies in the render but the preview clamps it, so judge on the rendered file. Prefer pre-normalising
  quiet assets. Long assets need an explicit `durationInFrames` or they ring past the action.
- Measure each SFX file's attack (first sample above ~−30 dB of its peak) and start the file that early; then subtract the
  output offset: `from = targetFrame − peakLatency − outputOffset`. Uncompensated, one film's biggest hit landed 0.27 s late.
- Sub-second tones (beeps, clicks) are better synthesised than generated; AI sound generation turns very short sounds to mush.
- **Sound comes after picture lock.** Any change to shot timing re-pins the SFX table. Keep it declarative
  (`{from, src, volume}` rows, each commented with its visible action); the video-director template's `sfx.ts` derives `from` from the
  timeline, which removes most re-pinning.
