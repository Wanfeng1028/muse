# VO-sync reference

Goal: the visuals **land on the spoken words**, and the timeline is **tight** (each scene lasts about as long as its narration — no long voice-less gaps).

## The loop
1. **Write VO that names things in the order they appear.** If a scene raises cards A→B→C, mention A, then B, then C in that sentence. This makes word-anchoring 1:1. (When you can't name everything, see "spreading" below.)
2. **Generate VO with timestamps:** `python3 scripts/elevenlabs.py tts script.json vo --voice <id>` → `vo/<NN>_<id>.mp3`, `vo/durations.json`, `vo/alignments.json`.
3. **Compute timing:** edit the `CONFIG` in `scripts/compute_timing.js` (scene order + cue→keyword), run it → `timing.json` with per-scene `start`/`dur` and per-cue `at`.
4. **Feed it to your engine.** Two clean ways:
   - emit a `timing.js` (`window.__TIMING = …`) the page reads at boot (works under `file://` and a server), or
   - have the page `fetch('timing.json')`.
   Use `dur` for scene length, `at` for when each cue fires.
5. **Build audio to the same timeline** (see the `audio-stems` skill): place each SFX at `scene.start + at` so it hits exactly on the word.

## Why VO-driven durations
Authoring fixed scene lengths and hoping the VO fits leaves dead air (or clips the voice). Instead derive `dur = head + voLen + tail` (clamped up to fit the last cue + any long sub-animation). Result: continuous narration, no silent stretches.

## Anchoring details
- `head` (~0.3s): the VO starts slightly after the scene opens so a headline can read first. A word spoken `w` seconds into the clip lands at scene-time `head + w` → that's the cue `at`.
- If your engine has a "lead/hero" hold before content appears, derive it from the first cue: `lead ≈ head + firstWordTime − 0.5` so the content slides in just as the narration reaches it.
- **Spreading** unnamed cues: anchor the named cards on their word; for the gaps, linearly interpolate `at` between the surrounding anchors (keep engine order). Feels synced without naming every item.
- **Snap-to-instant** (a list/grid that should all turn green at once when the VO says "auto-mapped"): set all those cues to the trigger word's time + tiny 0.06s increments.

## Gotchas
- `alignments.json` is **per-character**; find a word by `chars.join().toLowerCase().indexOf(word)` → `start[idx]`. Spelled-out acronyms ("P I I", "G D P R") are searched as written in the script.
- Regenerating one line shifts every downstream scene start — recompute timing and rebuild audio (cheap). Re-render the video only when the visuals are locked.
- ElevenLabs voice settings live in `elevenlabs.py` (stability/style); the `with-timestamps` endpoint returns the alignment used here.
