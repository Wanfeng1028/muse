# Audio timing: choose only the needed depth

## Existing or manually annotated timing

For simple procedural visuals, listen to the selected excerpt and mark its
phrases, major accents and section changes. Import a supplied beat grid when
it refers to the same edit. Derive cue times from the real excerpt, not from
an assumed constant BPM when the track changes tempo. This route needs no
large-model download.

## Automated beat and energy analysis

Use an available analyzer for beats/downbeats, onsets and band energy. Store
its version and input audio identity in the brief. Normalize energy using
a documented rule so the visual mapping has a known range; do not confuse
different tracks' relative normalized energy with absolute loudness.

Listen at the intro, a busy passage, a section change and the end. Correct
half/double-tempo grids, pickup offsets, missing beats and false onsets where
they affect direction. Map only needed outputs into the v1 interchange; retain
downbeats/onsets as native sidecars when the chosen renderer uses them.

## Lyrics and stems, only when the visuals need them

For lyric typography, lock the transcript first. Line-level reveal can use
line times; karaoke or per-glyph wipes require reviewed word times. A forced
aligner (for example CTC) aligns a known transcript; a transcription model
(for example Whisper) provides an independent listening/check aid, not truth.

Stem separation is useful when vocal/instrument cues are otherwise masked,
but is optional. Inspect model/license, hardware and download size before
installing; disclose required downloads and stop if unavailable. Compensate
for any separation/resampling offset and confirm the result against the
original playback audio. Review quiet words, repeated phrases, backing vocals,
language changes and sung pauses. Preserve unreviewed points as unresolved.

The pdoom reference project ships song-specific timing. New music needs fresh
timing and native data integration. Its model pipeline is one implementation,
not a prerequisite for this Skill.
