# GUI Vision

This is a product vision for a future graphical workflow. Treat it as a north star, not a fixed spec.

## Core Idea

The perfect GUI is a music-first edit cockpit: song structure on top, source footage on the side, generated edit variants in the middle, and QA always visible. It should feel like an assistant for choosing and shaping the edit, not a traditional NLE replacement.

## Main Workspace

### 1. Song Map

A horizontal timeline shows waveform, energy, sections, beat markers, cut priorities, and suggested edit windows. The user can drag a `30-40s` window and immediately see expected cut density and section labels.

Key interactions:

- click marker to preview beat/cue
- drag target window
- toggle primary/secondary markers
- mark moments as drop, fill, button, breath, or peak

### 2. Footage Boards

Source clips are grouped by role: action, reaction, lasers, texture, menus/context, alternates. Each clip shows thumbnail strips, motion/glow score, provenance, duration, and crop-readability status.

Key interactions:

- promote/reject clips
- tag roles
- scrub a candidate moment
- pin a clip to a specific musical marker
- compare candidate starts side by side

### 3. Edit Variant Wall

The GUI generates several named variants, each with a mood, source mix, cut density, accent strategy, and contact-sheet preview. The user can choose a route before spending time on full renders.

Useful variant cards:

- title/mood
- format and duration
- source/kind mix
- marker coverage
- contact sheet
- quick render preview
- QA status

### 4. Timeline Detail

Once a variant is selected, a detailed segment timeline shows every cut as a colored block. Color means source role; height or badge means musical priority.

Key interactions:

- swap source for a segment
- lock a segment
- nudge source start
- change speed
- convert an accent slot back to main action
- rerender only affected segments

### 5. QA Panel

QA is not an afterthought. It is a persistent panel that warns about missing audio, wrong dimensions, weak cut density, overused sources, bad crops, generated placeholders, or visual-review notes.

## Ideal Flow

1. Drop in a song.
2. Analyze song and choose target window.
3. Add footage folders, Photos exports, or source lists.
4. Build review pack and promote clips.
5. Generate 3-5 edit variants.
6. Pick one, lock favorite moments, revise weak beats.
7. Render final.
8. QA with specs, contact sheet, source mix, and visual notes.
9. Export final plus timeline CSV, brief JSON, and contact sheet.

## Design Personality

The GUI should feel fast, visual, and decisive. It should not look like a marketing page or a generic dashboard. Think dense creative workstation:

- dark neutral canvas with clear media previews
- color used for roles and warnings, not decoration
- readable timelines and compact controls
- contact sheets and thumbnails always large enough to judge motion
- minimal prose; let the media, markers, and QA badges carry the interface

## Extensibility

Do not hardcode the workflow to Smash, lasers, or one kind of social edit. The role system should be editable:

- any source role can be added
- scoring rubrics can be changed
- target formats can be saved as presets
- variant strategies can be added as recipes
- future creative ideas can override the defaults without deleting the old pattern
