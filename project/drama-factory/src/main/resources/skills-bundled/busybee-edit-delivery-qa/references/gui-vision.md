# GUI Vision

This reference focuses on the QA and delivery portion of a future GUI.

## Core Idea

QA should feel like a final preflight panel for creative work. The user should see, in one place, whether the edit is technically correct, visually clean, musically aligned, and safe to deliver.

## Layout

### Final Preview

Large playback area with quick scrubbing and marker jumps. The user can jump directly to flagged segments.

### Contact Sheet Strip

A generated contact sheet or thumbnail strip appears beside the preview. Clicking a frame jumps the video to that time.

### Specs Card

Compact specs:

- duration
- aspect ratio
- resolution
- FPS
- audio present
- codec/container
- platform preset match

### Timeline Health

Shows:

- segment count
- average segment length
- source mix
- kind mix
- priority-hit coverage
- accent ratio

### Issues

Flags are grouped as:

- technical
- visual
- musical/timing
- source/provenance
- delivery/platform

Each issue should have a suggested action, not just a warning.

## Best Interaction

The user should be able to approve, request revision, or rerender from the QA screen. A good flow:

1. Run automated QA.
2. Review contact sheet.
3. Watch flagged moments.
4. Add human notes.
5. Choose `ready`, `revise`, or `rerender`.
6. Export final report with video, brief, timeline, and contact sheet.

## Extensibility

QA thresholds should be presets, not fixed rules:

- dense social montage
- cinematic cut
- internal proof
- public delivery
- platform-specific presets

Future creative ideas should be able to define their own QA rules.
