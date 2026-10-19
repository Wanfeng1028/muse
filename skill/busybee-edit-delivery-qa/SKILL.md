---
name: edit-delivery-qa
version: 1.0.0
description: Verify final video edits before delivery. Use when an agent needs to inspect a rendered MP4/MOV/WebM, confirm duration/resolution/frame rate/audio, generate or review contact sheets, analyze timeline CSVs, check cut density/source mix, check FX integration and cohesion, verify text-to-beat sync, catch weak frames or accidental placeholders, and decide whether a beat-synced social edit is ready to show.
---

# Edit Delivery QA

## Overview

Use this skill before presenting a video edit as finished. The expected output is a concise QA readout: technical specs, timeline health, visual review notes, and any fixes needed before delivery.

## Required Checks

1. Probe the final render:
   - duration
   - resolution
   - frame rate
   - video codec
   - audio stream presence
   - delivery container
2. Generate a contact sheet if one does not already exist.
3. Review the contact sheet for:
   - active, intentional frames
   - no title cards/interviews/blank frames unless deliberate
   - no watermarks or stock-preview overlays
   - readable subject/action after crop
   - accents that look intentional, not random filler
4. Inspect the timeline CSV if available:
   - segment count
   - average/min/max segment duration
   - source mix
   - kind/category mix
   - priority-hit usage
5. Compare the result to the target format and creative brief.
6. State whether the edit is ready, needs a small revision, or needs a rerender.

## Beat-Synced Montage Targets

For dense social montage cuts:

- Duration: usually `30-40s`.
- Vertical: `1080x1920`; landscape: `1920x1080`.
- Frame rate: `30fps` minimum.
- For a `35s` high-energy montage, `70-90` segments is healthy if the footage can support it.
- Average segment length: about `0.35-0.50s`.
- Audio should be present and clean.
- Contact sheet should show mostly active/intended footage.

## Integrated-FX & Craft Checks (2026-07 additions)

For edits with effects or text layers, add these to the required checks:

- **Cohesion / sticker check:** does any composited element read as an untracked sticker rather than an object in the scene? Does any segment read as a cutaway to a different video? Does one shot break the shared grade (a one-off look among naturals)? Any yes = revision — these are the highest-frequency rejection causes.
- **Text-sync check:** if a hook line is meant to land on a beat, measure the actual offset between the text-appearance frame and the audio accent; |offset| > 100ms = re-render.
- **Loop check:** replay the ending into the start; loop-seam edits must be invisible.
- **Phone-scale check:** inspect at full size AND phone scale; save review frames at mandated timestamps (e.g. 1/4/8/12/14s of a 15s piece) plus a late-frame spot check alongside the QA report.
- **Cheap-proof stage (before full builds, not after):** render a low-res skeleton of the first 3-5 seconds and watch it at scroll speed before committing to the full/VFX render — kill criteria are cheap at this gate and expensive after VFX.
- **QuickTime deliverable:** when the review happens in Apple players, also produce and separately QA a QuickTime-compatible .mov.
- For anything going public, run five independent gates: technical, visual, narrative, originality/rights, platform package. Automated QA supports but never replaces watching the render at normal speed. Grain is fine (viewers prefer it); blockiness, banding, upscale blur, watermarks, and borders are the real penalties.

## Failure Patterns

Send the edit back for revision when you see:

- no audio stream or wrong audio excerpt
- wrong aspect ratio or unintended crop
- empty frames, title cards, interviews, stock watermarks, or price overlays
- action hidden by the vertical crop
- too many weak crowd/laser/nature inserts replacing the main premise
- priority musical hits served by low-motion footage
- timeline CSV and final render disagree materially

## Script

Run `scripts/qa_video_edit.py` against the final video. Add `--timeline` and `--contact-sheet` when available:

```bash
python3 scripts/qa_video_edit.py final.mp4 --timeline final_timeline.csv --contact-sheet final_contact_sheet.jpg --out final_qa
```

The script writes JSON and Markdown. It can also create a contact sheet with FFmpeg when `--make-contact-sheet` is set.

## Human Review

The script catches specs and timeline problems; it does not replace watching or inspecting frames. Always pair automated QA with at least a contact-sheet review, and watch the final render when the edit is high stakes or visually dense.

For the Conteto Machino standard, read `references/edit-qa-standard.md`.

Optional references:

- `references/qa-thresholds.md`: adaptable thresholds by edit type.
- `references/example-prompts.md`: reusable final-QA prompts.
- `references/gui-vision.md`: product vision for a visual QA and delivery panel.
