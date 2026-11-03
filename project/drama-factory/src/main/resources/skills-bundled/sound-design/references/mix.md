# Mixing and mastering

Ducking, the offline mix, loudness, and diagnosing a voice you can't hear.

Contents
1. Ducking
2. The mix
3. Loudness and mastering
4. Diagnosing a voice you can't hear

---

## Ducking

- The bed drops 8 to 15 dB under the voice (more for dense music) with a slow release (music snapping back the instant a word ends sounds
  mechanical). Merge speech gaps shorter than ~0.6 s so the bed doesn't pump between phrases.
- The voice lives at 1 to 3 kHz: where possible, dip the bed there instead of (or as well as) pulling the whole level.
  The offline mixer does this (6 dB level + 3 dB extra above 3.5 kHz by default, attack 80 ms, release 600 ms).
- Keep the sidechain voice-only; an SFX in the voice group makes the bed duck under whooshes.
- An envelope that begins before the voice needs an explicit open level at t=0.
- If it sounds notched rather than quieter, the carve is too strong.
- Check every word is intelligible on phone speakers.

In-component ducking for drafts (Remotion volume is linear 0 to 1; interpolate in dB; the callback's frame is relative
to when that audio starts):

```tsx
const OPEN_DB = -10, DUCK_DB = -20;
const PRE = 4, ATTACK = 6, RELEASE = 18;            // frames at 30 fps
const dbToGain = (db: number) => Math.pow(10, db / 20);
const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
const bedDb = (f: number) => voSegments.reduce((db, s) => {
  const down = interpolate(f, [s.start - PRE - ATTACK, s.start - PRE], [0, 1], clamp);
  const up = interpolate(f, [s.end, s.end + RELEASE], [1, 0], clamp);
  return Math.min(db, OPEN_DB + (DUCK_DB - OPEN_DB) * Math.min(down, up));
}, OPEN_DB);
<Audio src={staticFile('audio/music/bed.mp3')} from={BED_FROM}
  volume={(mediaFrame) => dbToGain(bedDb(mediaFrame + BED_FROM))} />
```

## The mix

For finals with voice, music and SFX, mix offline and play one WAV in Remotion:

1. `npx tsx tools/export_cues.ts --variant main` → `out/cues.json`. The exporter reads the same timeline helpers the
   scenes animate with, so picture and sound cannot drift, and it refuses to write when two VO lines overlap or sit closer
   than 0.15 s. Schema: `scripts/cues.schema.md`; paths are relative to `public/`; an SFX `at` is the film second its
   transient peak should land on.
2. `scripts/mix.py out/cues.json --out public/audio/mix-main.wav --json` → the mix, `out/stems/*.wav` and a report
   (LUFS, plus SFX audibility: it fails when event sounds sit too far under voice and music)
   (`--check` validates the cues and resolves files without mixing). Defaults: VO −16 LUFS, bed −19 LUFS in the gaps,
   ducking as above, SFX peak-aligned, two-pass loudnorm to −14 LUFS / −1 dBTP.
3. In the video-director project template, `Main.tsx` plays `public/audio/mix-<variant>.wav` when it exists; otherwise it falls back to draft
   audio (music with an in-component duck, any recorded VO, SFX files), which does not peak-align SFX. Masters always use
   the offline mix.

- Check with `scripts/audio_qa.py out/mix.wav --envelope <start> <end> 0.1` around every sync point: a hit lands, the duck
  works, a split sits in silence, the tail fades.
- Write stems (voice, product audio, SFX, music) for revisions and delivery.
- With music, deliver two masters from the same timeline: with and without the bed (SFX kept), switched by an input prop,
  so the client can swap the music.
- Ramp the music out before a stinger or end card rather than letting its tail decay under the CTA. Measure loudness per
  section: an end card 15 dB under the dialogue is a bug.
- Drafts and simple overlays may mix in-component with `volume` callbacks.

## Loudness and mastering

- Social and web: integrated −14 LUFS, true peak −1 dBTP, LRA 11, two-pass `loudnorm` (pass 1 `print_format=json`, pass 2
  feeds the measured values with `linear=true`). Podcasts −16 LUFS. Broadcast differs (EBU R128 −23 LUFS).
- Measure the encoded MP4, not only the WAV: AAC encoding can push the true peak up (`scripts/audio_qa.py final.mp4`).
- Peak normalising is not loudness normalising.
- Chain order for voice or bed cleanup: subtract (rumble, mud) → level (compression) → relationships (duck, carve) →
  character → ceiling (limiter last).
- Final audio: AAC 320k at 48 kHz.

## Diagnosing a voice you can't hear

- You can't judge one unknown voice's absolute spectrum. Compare inside the same file: pauses vs speech, the file
  against its own median over time.
- Pauses reveal additive problems (hum, hiss, room tone) only.
- If the evidence is ambiguous, say so and offer 2 to 3 readings instead of inventing a cleverer measurement.

| Symptom | Band | ffmpeg fix |
|---|---|---|
| hum, rumble | 20 to 80 Hz | `highpass=f=80` |
| boomy | 80 to 250 Hz | `equalizer=f=200:t=q:w=1.4:g=-4` |
| muffled, boxy | 250 to 600 Hz | `equalizer=f=400:t=q:w=1.4:g=-3` |
| words hard to make out | 2 to 5 kHz | `equalizer=f=3000:t=q:w=1:g=2.5` or carve the bed |
| harsh | 3 to 5 kHz | `equalizer=f=3200:t=q:w=1.6:g=-3` |
| sibilant | 5 to 10 kHz | narrow cut 5 to 9 kHz, Q 3 to 4, −3 to −5 dB |
| hiss under speech | none | needs a better source |
