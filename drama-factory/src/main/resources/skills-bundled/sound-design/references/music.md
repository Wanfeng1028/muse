# Music

Choosing, analysing, editing and syncing music.

Contents
1. Music selection
2. Music analysis, editing and beat sync

---

## Music selection

- With a voice, the voice is the clock and the music is edited around it. Without one, pick the music first and build the
  beat map on it.
- Choose tracks with an energy event (a drop, hit or lift) and plan the key visual on it.
- Tempo as mood: 60 to 80 BPM regal, 90 to 110 smooth, 115 to 123 sophisticated, above 125 hype.
- Selection loop: shortlist 20 to 50 tracks, run an audio-model listening round with a fixed card (instruments, style,
  lift time, generic-stock 1 to 10, warmth, bounce, fit 1 to 10, one-line verdict; `media_judge.py music-fit`), then
  analyse the finalists. If everything sounds like generic stock, search again with cultural or genre terms instead of
  moods ("cumbia", "bossa", "lo-fi house" rather than "upbeat").
- Describe finalists chunk by chunk (`media_judge.py chunks`: instruments, energy, vocals, events, VO-friendly) to find
  lifts, stops and vocal shouts that would fight the voice.
- Sources: Pixabay (licence forbids standalone redistribution: don't commit it; keep the URL in the README and gitignore
  the folder), Mixkit, ElevenLabs Music, licensed libraries. Keep a licence ledger.
- Premium films: soft timbres, not missing sounds; remove anything out of place, keep every animated event covered
  (`sfx.md`). Never ship silent unless asked.
- In a remake, never reuse the reference's music or voice.

## Music analysis, editing and beat sync

- `scripts/music_analyze.py track.mp3` → tempo, beats, bars, key, per-second energy, drop candidates, `track.beats.json`.
  Run it on the clean music file, never on the mix (voice and SFX throw the beat tracker off; it warns when tracked beats
  agree with the steady grid less than 50% of the time). Fix the bar phase with `--downbeat t`; use `--grid tracked` only for
  music whose tempo drifts.
- frames per beat = fps × 60 / BPM (120 BPM at 30 fps = 15 f; a bar = 60 f). Compute each beat from the origin, never
  by accumulating a rounded value (128 BPM = 14.06 f/beat drifts a frame every ~16 beats):
  `beatF(n) = round((t0 + offset + n·T) · fps)`. Keep times as float seconds and round only at the end.
- Don't trust a tracker's tempo value (one was 2% off: 129.2 vs 131.97). Fit a least-squares line `t_i = t0 + i·T` to the
  beat times, accept residuals ≤ ±15 ms, test the 0.5×, 1× and 2× grids and pick the one whose integer beats land on the
  kicks. On dense mixes, detect on a drum stem.
- Transient classes by band: kick (40 to 160 Hz) drives hits and slams; snare (150 to 500 Hz body, 1 to 3 kHz crack) drives
  replacements and cuts; hi-hat density (6 to 14 kHz) sets how busy micro-motion may be. Hits are a candidate pool, not a
  trigger list.
- Shot lengths in beats: 4 or 8, accelerating runs on half or quarter beats. Dense regular cuts use the grid; a lone accent
  or the final freeze uses the real transient (grid drift is amplified on a lone accent).
- Verify after rendering: extract the rendered audio, refit the grid, tabulate designed frame vs measured beat. Pass ≤ 3
  frames, ideal ≤ 1.5. At 30 fps the floor is ±16.7 ms; never claim better.
- **AAC priming delays the rendered audio**, typically ~2048 samples at 48 kHz (≈1.3 frames at 30 fps; one pipeline
  measured 4). Measure it once per pipeline by cross-correlating 2 to 3 sharp SFX, and keep it as a separate offset
  constant. A uniform same-direction offset on every cut is this, not the analysis.
- **Find the drop by energy**: per-bar low-band and full-band energy, then 20 to 50 ms windows around the jump
  (`--around t`). Never trust an auto beat grid; one measured grid was two beats off.
- Align: start the song at `dropInSong − dropInFilm`. In Remotion: `trimBefore={Math.round((dropInSong − dropInFilm) *
  fps)}`; if negative, delay with `from`.
- Snap tolerance: a reveal may move ≤ 0.15 s, a small entrance ≤ 0.10 s to land on a cue.
- Anchor key words to downbeats: start the line so that the brand name lands exactly on a phrase start (video-director template
  `timeline.ts` helpers).
- Edits (`scripts/music_splice.py`): cut on bar lines with an equal-power crossfade (~12 ms); stretch at most ~8% with
  pitch-preserving `atempo` offline rather than `playbackRate`.
- Every splice gets a blind test: the edited excerpt and an untouched control of the same length, shuffled, judged
  several times (`media_judge.py blind-splice`). One splice scored 9/10 noticeable against 0/10 for the control and was
  replaced.
- **Button ending**: play the arrangement to a downbeat, then cut to the track's own final hit and ring-out. It beat
  fading or cutting into a sparse outro.
- Fade in ~0.25 s; fade the tail over the last ~0.9 s on a power curve.
- Transitions: a riser into the cut, a bass hit on the cut.
- Tune pitched foley to the song's key (`music_analyze.py` estimates it; `foley.py --key`).
