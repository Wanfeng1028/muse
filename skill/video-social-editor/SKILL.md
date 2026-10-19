---
name: video-social-edit
version: 1.0.0
description: >
  Edits raw screen recordings into polished social media videos. Use this skill whenever
  the user has a screen recording (demo, walkthrough, tutorial, product showcase) and
  wants to produce a cropped, cut, focused video ready for social media — Instagram
  Stories, TikTok, LinkedIn, YouTube Shorts, or any platform. Handles all four phases:
  shot list → rough cut → reframe to target format → text overlays. Also generates
  voice-over scripts. Trigger on phrases like "edit this video", "make a social clip",
  "cut this recording", "crop for stories", "add text overlays", "make it 9:16",
  "reel from this demo", or any time the user shares a video file and wants it edited.
---

# Video Social Edit

Turns raw screen recordings into clean, focused social media clips. The workflow runs
in four phases — each one builds on the previous and can be reviewed before moving on.

## Quick reference

**Target formats** → see `references/social-formats.md`
**Crop geometry math** → see `references/crop-geometry.md`
**Overlay style presets** → see `references/overlay-styles.md`
**Reusable scripts** → see `scripts/` directory

---

## Phase 0 — Probe & Interview

Before touching the timeline, understand the source and the goal.

### 1. Probe the source video

```bash
ffprobe -v quiet -show_streams -show_format -of json "path/to/video.mov" 2>/dev/null
```

Extract: width, height, frame rate (r_frame_rate), duration. Report these to the user.

### 2. Ask the user (if not already clear)

- **Target format**: 9:16 (Stories/Shorts/TikTok), 1:1 (square feed), 16:9 (landscape), 4:5 (portrait feed)? Show the options from `references/social-formats.md`.
- **Content layout**: Where is the interesting action on screen? (e.g. "left side is the browser, right side is agent chat") — this drives crop decisions.
- **Rough duration target**: ~60–90s for stories, 3–10min for YouTube.
- **Overlay style**: dark pill (default), light pill, bottom bar, or none? See `references/overlay-styles.md`.
- **Voice-over**: Should the skill write a VO script per segment?
- **Privacy**: warn the user to flag any frames with personal info (emails, passwords, personal browser tabs) before you set cut points.

### 3. Extract sample frames to understand the layout

Pull one frame every 30s to build a mental map of what's on screen:

```bash
ffmpeg -i "video.mov" -vf "fps=1/30,scale=480:-1" -vsync vfr "frames/sample_%03d.jpg" -y 2>/dev/null
```

Read these frames visually before writing the shot list.

---

## Phase 0.5 — Listen (optional, gated)

Most screen recordings are silent, but some are **narrated live**. When the source carries
real audio, use it to seed a smarter shot list. Full details, output shapes, and setup are in
`references/listening.md` — read it if this phase applies.

**Always gate first:**

```bash
scripts/detect_silence.sh --video source.mov
```

If it returns `"has_audio": false` (no track, or effectively silent — the x402 demos measured
~−91 dB), skip this phase entirely and go to the shot list. Only continue when `has_audio` is true.

When there IS audio:
- **Tier 1 (no extra deps)** — the same command emits a `segments` list with `keep` / `cut` /
  `speedup` hints from silence detection. Use these to pre-fill the shot list's cut points.
- **Tier 2 (optional whisper.cpp)** — `scripts/transcribe.sh --video source.mov --out-prefix demo-transcript`
  emits a timestamped transcript. Read it to place segment boundaries where the narration
  shifts topic and to pull the **Voice-over** column from what was actually said. No-ops
  cleanly if whisper.cpp/model isn't installed, so Tier 1 always carries the phase.

These are suggestions that make Phase 1 smarter — you still decide final cuts against the visuals.

---

## Phase 1 — Shot List

Write a markdown table saved alongside the source video, e.g. `my-video-shotlist.md`.

Columns:
| # | Src in→out | Len | Speed | Focus | Overlay text | What's on screen | Voice-over |

**Focus values:**
- `LEFT` / `RIGHT` / `CENTER` — hard crop to that panel
- `ZOOM` — zoom into a specific region (file tree, code, a UI element)
- `PAN L→R` / `PAN R→L` — animated sweep between panels
- `FULL` — use the whole frame (for 16:9 targets)

**Speed presets:**
- `1x` — real time (talking, key moments, reveals)
- `1.5x` — comfortable walking pace (form filling, navigation)
- `8x` — montage (waiting, repetitive scrolling, install output)

**Rules for a good shot list:**
- Cut the first few seconds of setup/fidgeting and the tail after the last action.
- Remove waits, loading screens, and repetitive segments — use `8x` or cut entirely.
- Each segment should have ONE clear purpose — don't let a segment do two things.
- Flag any segments that contain personal info (emails, autocomplete popups showing real data, personal browser tabs) — exclude them.
- The VO column should be a punchy sentence per segment, present tense, no filler.

Review the shot list with the user before proceeding. Timing is much easier to fix here than after rendering.

---

## Phase 2 — Rough Cut

Build a landscape preview at the source aspect ratio (scaled to max 1440px wide) so the user can review pacing before the crop step. Saves re-rendering the expensive reframe if pacing needs fixing.

### Build the ffmpeg filter_complex

Each segment is a chain: `trim → setpts → fps=30 → scale`:

```bash
ffmpeg -y -i "source.mov" -filter_complex "
[0:v]trim=START:END,setpts=PTS-STARTPTS,fps=30,scale=1440:-2[s1];
[0:v]trim=START:END,setpts=(PTS-STARTPTS)/1.5,fps=30,scale=1440:-2[s2];
[0:v]trim=START:END,setpts=(PTS-STARTPTS)/8,fps=30,scale=1440:-2[s3];
[s1][s2][s3]concat=n=3:v=1:a=0[v]
" -map "[v]" -c:v libx264 -preset fast -crf 18 -t CAP_SECONDS "rough-cut.mp4"
```

**Important gotchas:**
- Use `scale=1440:-2` (not `-1`) to ensure even pixel dimensions for H.264.
- The concat output often runs slightly long due to keyframe rounding — always add a `-t` cap (total expected duration + 0.5s).
- Audio is dropped (screen recordings are usually silent or have system audio you don't want).
- Use `trim=` with seconds (not timecode): `1:06` = 66 seconds.

After rendering, spot-check key frames at the expected segment boundaries:

```bash
ffmpeg -ss TIME -i rough-cut.mp4 -vframes 1 -vf scale=480:-1 "check_TIME.jpg" -y 2>/dev/null
```

Show these to the user. Fix any cut points before Phase 3.

---

## Phase 3 — Reframe to Target Format

Apply the crop and pan geometry from `references/crop-geometry.md` for the chosen format.

Read the crop geometry reference now: it covers 9:16, 1:1, 4:5, 16:9 and explains the blurred-backdrop technique for panels that aren't naturally the target ratio.

### Build the reframe script

Same structure as the rough cut but replace `scale=1440:-2` with the crop + scale for the target format. Save as `my-video-reframe.sh`.

**For animated pans** (LEFT↔RIGHT), the crop `x` uses an `if(lt(t,...))` expression:

```
# R→L pan: hold RIGHT for 2s, sweep 0.667s to LEFT
x=if(lt(t\,2)\,RIGHT_X\,if(gt(t\,2.667)\,LEFT_X\,RIGHT_X-(RIGHT_X-LEFT_X)*((t-2)/0.667)))

# L→R pan: hold LEFT for 2s, sweep 0.667s to RIGHT
x=if(lt(t\,2)\,LEFT_X\,if(gt(t\,2.667)\,RIGHT_X\,LEFT_X+(RIGHT_X-LEFT_X)*((t-2)/0.667)))
```

- `t` resets to 0 at the start of each segment (after `setpts=PTS-STARTPTS`) — pan timing is local.
- Commas inside `if()` must be escaped as `\,` in a bash quoted string.
- 0.667s sweep = visually snappy without being jarring.

After rendering, spot-check: start of each segment, mid-pan frame, and the key money-shot segment.

---

## Phase 4 — Text Overlays & Final Render

### 4a. Generate title card PNGs

This ffmpeg build may lack `libfreetype` (no `drawtext`). Always use Pillow instead — it's reliable and portable. Run `scripts/generate_titles.py` — pass the overlay texts and style preset. It writes one PNG per segment into a `titles/` directory.

See `references/overlay-styles.md` for all style presets (dark pill, light pill, bottom bar).

**Two-line format works best:** keep each line under ~40 chars. Long single-line overlays shrink the font — splitting into 2 lines reads better on a phone.

### 4b. Calculate overlay timing windows

For each segment, the overlay enable window is:
- Start: `segment_start + 0.3s` (slight delay after cut)
- End: `segment_end - 0.2s` (clears before next cut)

Segments that share overlay text can use one PNG — extend the window across both.

### 4c. Composite and export

```bash
ffmpeg -y -i "reframed.mp4" \
  -i titles/title_01.png -i titles/title_02.png ... \
  -filter_complex "
[0:v][1:v]overlay=0:140:enable='between(t,0.3,4.8)'[v1];
[v1][2:v]overlay=0:140:enable='between(t,5.3,9.5)'[v2];
...
[vN-1][N:v]overlay=0:140:enable='between(t,X,Y)',format=yuv420p[out]
" \
  -map "[out]" -c:v libx264 -crf 20 -preset medium \
  -t DURATION "final.mp4"
```

- Overlay y=140 places the pill just below the top UI chrome — works for browser and chat-column content.
- Add `format=yuv420p` to the **last** overlay only (required for H.264 compatibility).
- Always add a `-t` cap to trim any frozen tail frames.

---

## Voice-Over Script

If the user wants a VO script, write one sentence per segment, present tense, no filler. Each line should be speakable in the segment's duration at a comfortable pace (~2.5 words/second). Output it as a clean standalone block the user can paste into a TTS tool or record themselves.

---

## Phase 5 — Voice-over, Facecam & Captions (optional, post-final)

Runs only after `*-final.mp4` is done and the user opts in. Read `references/voiceover-facecam.md` for the full details, recording steps, and script options.

The workflow: the user records **face + voice together in one QuickTime take**, narrating while the finished video plays. That single `.mov` carries both the voice-over (its audio) and the face (its video), already in sync. Then:

**5a — bubble + audio.** Overlay the face as a circular bubble and use the recording's audio as the sound track:
```bash
scripts/add_voiceover.sh --video final.mp4 --rec facecam.mov --corner <corner> --out final-vo.mp4
```
**Ask the user which corner** (`tl`/`tr`/`bl`/`br`). Use `--no-face` for audio only. `--offset` syncs a take that started early/late.

**5b — captions (opt-in).** Burn one caption per VO line, bottom-positioned, timed to each segment's window (same start/end numbers as the title overlays):
```bash
scripts/add_captions.sh --video final-vo.mp4 --lines captions.json --out final-vo-cc.mp4
```
`captions.json` is `[{text,start,end}, ...]`. **If captions are on, steer the user to a TOP corner for the bubble** — captions live at the bottom, so a bottom-corner bubble collides with them (face-top / captions-bottom is the standard reel layout).

Both scripts reuse the Pillow→PNG→overlay toolchain (this ffmpeg lacks libass, so burned `.srt` isn't an option).

---

## Deliverables checklist

- [ ] `*-shotlist.md` — reviewed and approved shot list
- [ ] `*-rough-cut.mp4` — landscape preview for pacing review
- [ ] `*-story-{format}.mp4` — reframed intermediate
- [ ] `titles/title_NN.png` — overlay PNGs
- [ ] `*-final.mp4` — **final deliverable (silent)**
- [ ] VO script (if requested)
- [ ] `*-final-vo.mp4` — with narration + face bubble (Phase 5, if requested)
- [ ] `*-final-vo-cc.mp4` — plus burned captions (Phase 5b, if requested)
