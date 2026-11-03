---
name: code-music-video
description: Design and produce music-driven videos with deterministic code scenes, shared audio timing, browser preview, and offline frame rendering. Use for code-rendered MVs, lyric typography, and procedural music visuals, not ordinary video editing or text-to-video prompting.
---

# Code Music Video

Turn a music track into a reproducible, inspectable video project. Keep the
production method independent of the renderer. This package supplies guidance,
an input template and a timeline validator; it is not a rendering engine.

Match the requested scope: a timing-only check reads the timeline contract,
runs the validator and reports its limits; it does not require a renderer or
a full creative brief. A plan-only job ends after the scene plan. An existing
project repair reopens the affected stage and downstream checks. Full
production follows the sequence below.

## Establish the job

Use the known inputs and ask only for missing decisions that change the work:

- Audio file and the exact excerpt; lyrics only when they will appear on screen.
- Intended feeling, visual concept, audience, and required recurring elements.
- Duration, aspect ratio, resolution, frame rate, and output format.
- Existing renderer, available runtime, and permitted installs/downloads.

For a new project, copy [assets/brief.template.md](assets/brief.template.md).
Record assumptions as proposals, not approvals. A planning-only request stops
at the plan; production authorization does not imply publishing authorization.
Keep third-party music, lyrics, fonts and footage separate from code licensing.

## Production sequence

### 1. Establish one audio clock

Measure the selected audio's actual duration. Record its trim offset and use
seconds from the excerpt's start as the common time origin. Every scene,
lyric cue and export range must refer to that same origin.

Read [references/contracts.md](references/contracts.md) before creating or
importing time data. Start with section boundaries and beats. Use supplied
timing or manual annotations when sufficient; an instrumental track needs no
lyric alignment. For automated analysis or word-synced type, read
[references/audio-analysis.md](references/audio-analysis.md).

Validate the interchange timeline:

```sh
python scripts/validate_timeline.py project/timeline.json
```

Exit when the data passes validation **and** spot-listening confirms section
changes and relevant cues against this audio file. Structural validity alone
does not prove musical accuracy. Empty beats are allowed for unmetered music.

### 2. Map musical changes to visual changes

Write a compact scene plan against the timeline. For each section record:
time window, emotional/semantic job, dominant subject or graphic motif, camera
or layout behavior, controlling audio signal, and the entry/exit transition.

Give each visual element a specific signal and range: bass can control scale;
a downbeat can trigger a cut; a sung word can reveal a glyph. These are design
choices, not mandatory mappings. Keep some visual parameters stable so the
music can be read instead of making everything pulse.

Exit when each section has a job and adjacent scenes have explicit handoffs.
Reuse the visual concept across sections while changing information, scale,
layout or energy. A new track requires new timing and direction, not just a
replacement audio filename.

### 3. Implement time-addressable scenes

Read the scene and adapter contracts in
[references/contracts.md](references/contracts.md). Inspect the selected
engine's actual API before writing code. For the optional Three.js-based
reference engine, read [references/pdoom-adapter.md](references/pdoom-adapter.md).
For another engine, map its capabilities to the same contract.

- Derive state from absolute music time `t`, scene-local progress and fixed
  seeds. Re-rendering a time must not depend on playback history or call count.
- Construct reusable geometry, text layouts and resources before capture.
- Keep randomness seeded. Use time-indexed events, not wall-clock timers.
- Clear or fully overwrite each output frame. Define transitions explicitly.
- If simulation history is unavoidable, declare the scene stateful and require
  reset plus fixed-step replay from a documented origin. Arbitrary-order
  sampling is then unsupported unless the adapter proves it works.

Exit when seeking forward, backward and directly to the same time yields the
same image on the tested runtime. Test first frame, a musical hit, a section
boundary and the last visible frame; compare matching-time preview/export
captures using the same resolution, sampling and color settings.

### 4. Preview and test a representative excerpt

Render stills around key cues and scene boundaries, then a short excerpt that
includes the hardest transition or motion. Judge the moving clip **with audio**:
cue sync, lyric legibility, composition, motion, cut reason and visual continuity.
Record concrete fixes at their timecodes. A contact sheet cannot approve motion
or synchronization; a typecheck cannot approve an image.

Exit when the excerpt plays with the expected audio, survives direct seeks,
and has no unresolved blocking sync, legibility or continuity failure. Check
logs for scene/render errors. Fix the responsible timing, scene or adapter;
do not use extra effects to conceal a failed handoff.

### 5. Render and verify the master

Freeze the code and timing data for the render. Disable live reload during
capture. Render each frame at the agreed dimensions and frame rate; keep frame
index, absolute music time and any sub-frame shutter sampling distinct.
Read the export contract in [references/contracts.md](references/contracts.md).

Long renders may use adjoining frame-index ranges. Give each frame to exactly
one segment. Stateful scenes need their specified replay before each segment;
they cannot start cold at an arbitrary boundary. Mux the original approved
audio once, or use sample-exact contiguous audio cuts when required.

Verify the encoded file's dimensions, frame rate, frame count, duration, audio,
first/last frame and every segment join. Inspect playback at sync anchors and
joins; investigate black frames, freezes, drift or gaps. Higher resolution must
be rendered at higher pixel dimensions, not relabeled or silently upscaled.

Deliver the project source, timing data, scene plan, final media, rerun commands
and a short verification result. Separate successful checks from untested
capabilities. Stop if a required adapter capability is absent or a render fails;
retain useful artifacts and report the smallest missing dependency.

## Package checks

```sh
python scripts/validate_timeline.py examples/timeline.json
python -m unittest discover -s tests -v
```

These check the timeline interchange, not a rendered MV. See
[SOURCES.md](SOURCES.md) for the reference workflow and limits of its transfer.
