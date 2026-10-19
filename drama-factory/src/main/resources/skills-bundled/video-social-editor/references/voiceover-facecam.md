# Voice-over, Facecam & Captions Reference

Phase 5 runs only after the silent `*-final.mp4` is done and the user opts in. It adds a
narration track and (optionally) a talking-head bubble and captions.

## The recording model

The user records **face + voice together in one QuickTime take**, narrating while the
finished video plays. That single `.mov` gives us both assets, already in sync:
- its **audio** becomes the voice-over track
- its **video** becomes the circular face bubble

No separate audio/video alignment problem — they were captured against the same playing cut.

### QuickTime recording steps (hand these to the user)

1. Open **QuickTime Player** → **File → New Movie Recording**.
2. Click the ▾ next to the record button; pick your **camera** and **microphone**.
3. Open `*-final.mp4` in a second window (or another player), ready at the start.
4. Press **record**, immediately play the final video, and read the VO script in time
   with the on-screen action.
5. Stop when the video ends. Save/export the `.mov` and send me the path.

Tip: the recording length should roughly match the video; small over/under is fine
(`--shortest` trims), and `--offset` fixes a start that drifted a beat early or late.

## Scripts

### add_voiceover.sh — bubble + audio (Phase 5a)

```bash
scripts/add_voiceover.sh \
  --video path/to/final.mp4 \
  --rec   path/to/facecam.mov \
  --corner tr \
  --out   path/to/final-vo.mp4
```

Options: `--corner tl|tr|bl|br` (default `br`), `--size` (px, default 320),
`--pad` (edge padding, default 40), `--offset` (± seconds to sync), `--ring-width`
(default 6; `0` = no ring), `--no-face` (audio only, no bubble).

How it works: center-crops the webcam to a square, scales to `--size`, applies a
Pillow-generated circular alpha mask (round bubble), overlays it at the chosen corner
with a ring, and maps the recording's audio as the sound track.

### add_captions.sh — burned captions (Phase 5b, optional)

```bash
scripts/add_captions.sh \
  --video path/to/final-vo.mp4 \
  --lines path/to/captions.json \
  --out   path/to/final-vo-cc.mp4
```

`captions.json` is an array of `{text, start, end}`, one per VO line, where start/end are
that line's window **in the final video** (take them from the shot list's segment
boundaries — same numbers as the title overlay windows). Runs after the VO mux so
captions sit on top of everything. Uses the Pillow→PNG→overlay toolchain (this ffmpeg
lacks libass, so a burned `.srt` isn't an option). `--bottom-margin` (default 210) sets
how far above the bottom edge the caption sits.

## Layout: corner choice when using captions

Captions live at the bottom. A **bottom-corner** bubble collides with them. So the rule:

> **If you're adding captions, put the bubble in a TOP corner (`tl`/`tr`).**

That's the standard reel layout anyway — face up top, captions along the bottom. Without
captions, any corner is fine (`br` is the default and least obtrusive).

## Bubble sizes

| Use | `--size` | Notes |
|-----|----------|-------|
| Subtle presence | 240 | Small, stays out of the way |
| Default | 300–320 | Readable face, doesn't dominate |
| Prominent host | 380–420 | Talking-head-forward content |

## Deliverables

- `*-final-vo.mp4` — final video + narration + face bubble
- `*-final-vo-cc.mp4` — the above plus burned captions (if requested)
- `captions.json` — the caption timing source (kept, so captions are re-runnable)
