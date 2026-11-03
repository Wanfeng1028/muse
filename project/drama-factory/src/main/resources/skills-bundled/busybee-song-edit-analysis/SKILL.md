---
name: song-edit-analysis
version: 1.0.0
description: Analyze songs and audio files for beat-synced video editing, clip timing, energy mapping, viral window selection, onset-locked cut grids, footage selection, and agent-readable edit briefs. Use when an agent needs to inspect an MP3/WAV/M4A/audio track, estimate tempo and beat grids, identify sections, produce cut markers, pick the best 15-30s window of a song for short-form video, or guide a human or another agent in choosing footage that matches musical energy.
---

# Song Edit Analysis

## Overview

Use this skill to turn a song into practical editing intelligence: tempo, beat grid, section map, energy curve, cut priorities, footage-fit notes, timeline markers, and an agent-facing footage selection brief.

The bundled script is the default path because it keeps the analysis reproducible and gives both human-readable and machine-readable outputs.

## Workflow

1. Confirm the audio path and create an output folder for deliverables.
2. Ensure Python dependencies are available: `librosa`, `numpy`, `scipy`, `matplotlib`, `pandas`, `scikit-learn`, and `soundfile`.
3. Run `scripts/analyze_song_for_editing.py <audio-file> --out <output-folder>`.
4. Inspect the generated energy timeline image and section CSV. If the automatic sectioning over-splits a busy section, synthesize a simpler macro section map in the final response or a separate markdown file.
5. Use the agent footage brief when another agent will choose clips, assemble an edit, or score footage candidates.
6. For downstream production, use `$footage-review-pack` to curate sources, `$beat-synced-montage-builder` to assemble the edit, and `$edit-delivery-qa` to verify the final render.

## Script Outputs

For an input named `my_song.mp3`, the script writes:

- `my_song_beats.csv`: every detected beat with time, estimated bar/beat position, energy, bass, brightness, transient strength, and cut priority.
- `my_song_cut_markers_30fps.csv`: primary and secondary cut markers with 30fps timecode and concise marker notes.
- `my_song_sections.csv`: detected structural regions with average energy, sonic character, footage fit, and cut strategy.
- `my_song_phrases.csv`: 8-beat phrase-level editing notes.
- `my_song_energy_timeline.png`: waveform, energy curve, footage cues, and detected sections.
- `my_song_editing_guide.md`: human-readable editing guidance.
- `my_song_agent_footage_brief.json`: structured footage-selection instructions for another agent.
- `my_song_analysis.json`: machine-readable overall summary.

## Onset-Locked Cut Grids (v2 engine, preferred for dense cutting)

When the edit should cut on every moment the song enables (rapid bursts included), skip marker thresholds and build a raw onset grid:

```python
env    = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
onsets = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=512,
                                    backtrack=False, delta=0.02, units="time")
```

`delta=0.02` catches everything (0.03-0.04 for cleaner grids). Merge onsets closer than 0.13s keeping the stronger; quantize to frames with `int(round((t-t0)*FPS))`; force a cut at frame 0; drop cuts within 2 frames of the end. Hold when sparse, burst when busy — never insert off-grid filler cuts. Onsets in the top quartile of strength earn accents (punch-in zooms). Snap any estimated beat grid to the nearest real onset when within 60ms (transients sit up to ~35ms off a steady-tempo grid); for transform/style-switch moments quantize with floor, not round, so the change lands on the frame containing the transient.

## Viral Window Selection (which 15-30s to cut)

Score candidate windows on five signals: repetition/chorus-ness (beat-synced chroma self-similarity, diagonal + 8 off-diagonals zeroed, row-mean), energy rise (`post_mean(4s) - pre_mean(4s)` — finds build→drop), loop seam (cosine similarity of chroma+mfcc just after window end vs just after start — invisible loops), lyric placement (a phrase starting within [start-0.5, start+3.0], boosted by emotional words), and the artist's own posted start-time prior. Anchors = top repetition peaks + top energy-rise beats + the prior, each snapped to the bar downbeat at or just before it so the hook lands early. Combine roughly `0.26*energy + 0.20*repetition + 0.18*rise*2 + 0.16*lyric + 0.12*loop_seam + 0.08*prior`; keep top windows overlapping <50%.

## Envelope Followers (drive continuous FX)

For audio-reactive effects, resample the onset envelope to the frame grid, normalize by the 95th percentile, then a one-pole peak-hold (instant attack, `exp(-1/(fps*0.22..0.25))` decay). Beat pulses for punch-zoom/bloom: per beat add `amp * exp(-(t-t_beat)/0.16)`, amp energy-weighted. Keep bass / energy / high / transient as separate normalized channels — never one loudness scalar — and leave onset event channels unsmoothed. Render FX against the exact same start/duration window as the edit so pulses and cuts share one envelope (sync by construction).

## Interpretation Rules

Treat tempo, beats, and bars as estimates until checked against the waveform or by ear. Beat grids are usually good enough for rough editing, but downbeat labeling can be offset by a beat or phrase.

Use this energy ladder for footage selection:

- Energy 1 / very low: atmosphere, titles, detail shots, slow pans, quiet setup.
- Energy 2 / low: preparation, anticipation, context, slow motion, pre-action.
- Energy 3 / medium: visible movement, reactions, rhythmic B-roll, 2-4 beat cuts.
- Energy 4 / high: active movement, impact-adjacent shots, fast B-roll, 1-2 beat cuts.
- Energy 5 / peak: strongest footage, collisions, reveals, fast whips, VFX hits, rapid alternation, 0.5-1 beat cuts.

Use primary cut points for major subject changes, impacts, hard cuts, reveals, speed-ramp landings, and title hits. Use secondary cut points for angle changes, continuation cuts, smaller B-roll swaps, and speed-ramp starts.

## Agent Footage Selection

When an agent will choose footage, pass it `*_agent_footage_brief.json` plus any available footage inventory. Instruct the agent to:

1. Tag each candidate clip with `content_type` from the brief taxonomy.
2. Score each candidate clip with `motion_intensity` from 1-5.
3. Match clip intensity to each section's `energy_level`, allowing plus/minus 1 unless the edit needs deliberate contrast.
4. Reserve `peak_impact` and motion-intensity 5 clips for the highest-energy section.
5. Place subject changes, impacts, and reveals on primary cut points.
6. Use shorter durations, tighter crops, speed ramps, or repeated impact details when the available footage is less intense than the music.

## Human-Facing Guidance

Always provide a concise macro map in addition to raw data. Editors need musical judgment, not just a list of beats. Call out:

- Where to hold shots.
- Where the first meaningful rhythmic cuts begin.
- Where the drop or peak begins.
- Which section deserves the best footage.
- The strongest cut points by timestamp.
- Any uncertainty, especially if section detection over-splits or if the downbeat may be offset.

## Downstream Skills

This skill produces the musical intelligence. Use the companion skills for the rest of the repeatable workflow:

- `$footage-review-pack`: build shortlists, review galleries, manifests, and source provenance.
- `$beat-synced-montage-builder`: map footage to cut markers and render social montage variants.
- `$edit-delivery-qa`: inspect final renders, contact sheets, timeline density, and delivery readiness.
