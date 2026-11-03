# Guided flow — PODCAST

Two speakers on camera as animated avatar images, lip-synced to a `[Interviewer]` / `[Interviewee]` dialogue. Follow `README.md` protocol. Tool semantics: `references/project-workflows/podcast.md`.

**Route here when:** "AI podcast", two-person dialogue video, interview video, host + guest, debate/Q&A between two people.
**Route away:** one person to camera → `avatar`; narrated scenes with no faces → `text-to-video`; cutting an existing recording → `clipping`; visuals for a song → `music-video`.

**Non-negotiables the wizard must enforce** (the UI does NOT block Create Video on them; the renderer hard-fails):
- **BOTH avatar images are required** — interviewer AND interviewee, files must exist on disk.
- Script **more than 10 chars** after trimming (the renderer fails on `<= 10`, so 10 itself is rejected — 11 is the first accepted length; same floor as the avatar script since 2026-08-19). Every non-empty line must read `[Interviewer] text` or `[Interviewee] text` with a space after `]`, and both roles must appear — this is enforced by the MCP tool (case-insensitively); the desktop app itself is laxer, so a script that works in the UI can still be rejected over MCP. Normalize before sending.

## Question sequence

### Q1 — Topic or script
"What's the podcast about — or do you already have the dialogue?"
- If they paste tagged dialogue → validate the strict format (fix lines that miss the space after `]`), skip Q2.
- If they give a topic/notes → the wizard writes the dialogue itself in strict form (there's no MCP tool for the in-app generator; the agent IS the generator). Always start with `[Interviewer]`, alternate naturally, confirm the draft before saving.

### Q2 — Conversation length (only when we write the dialogue)
1. **~1 minute (~150 words)** (Recommended)
2. ~2 minutes (~300 words — the in-app generator's default)
3. ~4 minutes (~600 words)
4. ~8 minutes (~1,200 words)

Caps: 2,000 words / 20,000 chars. Runtime ≈ 150 wpm. One billed avatar clip per line, and whole-second rounding makes **short lines disproportionately expensive** (a 2.1 s line bills as 3 s).

**Hard per-line limit — the podcast renderer never splits a dialogue line.** Unlike the avatar flow (which auto-splits a long script at silence and stitches it), each line here is sent whole to the avatar model. A line past the model cap **fails**, and the render degrades silently: in split view it falls back to a looped idle clip with no lip-sync, and in talking-only mode to a **black frame with audio**. Keep every line under **~60 words (~24 s) on OmniHuman 1.5** or **~140 words (~55 s) on either Kling model**. When drafting, break long answers into several shorter tagged lines instead of one paragraph — and check a user-supplied script for over-long lines before saving it.

### Q3 — Format (changes what the layout options mean)
1. **Vertical 9:16 — TikTok/Reels/Shorts** (Recommended; app default) — "Show Both" stacks top/bottom
2. Horizontal 16:9 — YouTube — "Show Both" is side-by-side
3. Square 1:1 — Instagram — **forces fullscreen single-avatar regardless of display type**

### Q4 — Avatar display type (its own question, straight after the format)
"How should the two speakers appear on screen?"
1. **Both on screen at once** (Recommended) → `Show Both Avatars` — never cuts, so transitions do nothing; adds exactly **2 idle clips (~4 s each)** to the bill, one per speaker.
2. Cut to whoever is talking — TV interview style → `Show Only Talking Avatar` — fullscreen single speaker, enables cut transitions, no idle-clip cost.

Word the options in the format they just chose — "side-by-side" for 16:9, "stacked top and bottom" for 9:16 — instead of the generic word "split".

**IF Q3 = 1:1** → the app renders fullscreen single-avatar whatever this is set to. Worse, the idle-clip cost is keyed on the display type **alone**: a 1:1 project left on `Show Both Avatars` still generates and bills 2 idle clips it never shows. Recommend option 2 on square projects for that reason, not just for tidiness.

This answer gates the transitions question in Q7 — skip transitions entirely for `Show Both Avatars` on a non-square project, where they are a no-op.

### Q5 — The two speakers (host, then guest; both MANDATORY)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template A) when `show_widget` exists: two cards — *Interviewer* and *Interviewee* — both required, both with *Generate with AI*; `extensions: ["jpg","jpeg","png","webp"]`. Never continue with an empty slot. Only if no `show_widget` tool can be found: use the options below.
For each role:
1. **Generate with AI from a description** (Recommended; suggest matching styles so the two heads look coherent)
2. A photo of a specific real person (≤3 face reference photos, JPEG/PNG/WebP → identity-preserving generation)
3. An image file I have (`select_podcast_avatar_image` accepts `.png .jpg .jpeg .webp`; TIFF is UI-only)
4. A stylized preset look (same 33-preset strip as the Avatar Creator)

Never reach the summary with an empty slot.

### Q6 — Voices (fetch live — no static list)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template C) when `show_widget` exists: one widget per role (title "Interviewer voice", then "Interviewee voice"); pre-filter to the pairing recommended here. Only if no `show_widget` tool can be found: use the options below.
`list_elevenlabs_voices` first, then offer pairings:
1. **Warm male host + bright female guest** (Recommended)
2. Bright female host + warm male guest
3. Two male voices (different timbre)
4. Two female voices (different timbre)

Offer per-role TTS previews (`generate_tts_preview`). BYO ElevenLabs key → cloned voices available, TTS bills their own EL account. Adapt the pairing to anything the user said about the speakers.

### Q7 — Camera motion (+ transitions when Q4 allows them)
**Camera motion:** 1. **None** (Recommended) · 2. Handheld · 3. Slow Zoom.
**Transitions** — ask ONLY when Q4 = `Show Only Talking Avatar` or the project is 1:1: 1. **None** (Recommended) · 2. One subtle light leak · 3. Mix of 3 · 4. All 20 (`Transition01`–`Transition20`; each carries a whoosh at the Sound Effects volume).

### Q8 — Quality + extras (batch)
> **WIDGET STEP — mandatory when `show_widget` exists (it may be deferred: ToolSearch for it first; see `widgets.md`). Do not call the file picker or write the setting until the widget's button phrase comes back.** (Template B) when `show_widget` exists: avatar-model cards (Kling Avatar Pro · Kling Avatar · OmniHuman 1.5) — the pick still goes to `set_avatar_settings`, not `set_podcast_settings`; ask subtitles + look note with the question tool afterwards. Only if no `show_widget` tool can be found: use the options below.
**Avatar model** (biggest cost lever — set via `set_avatar_settings`, NOT `set_podcast_settings`):
1. **Kling Avatar Pro — balanced** (Recommended)
2. Kling Avatar — cheapest
3. OmniHuman 1.5 — highest quality, most expensive per second (also the tightest per-line limit — see Q2)

**Subtitles:** yes, default style (Rec for 9:16) / no.
**Look note (optional, → PromptBar):** nothing (Rec) / modern tech-podcast / moody documentary / calm-wellness — steers the per-line B-roll stills, never the dialogue. Warn: never paste the transcript into the PromptBar.

## Summary + confirm

Per `README.md` contract. Include: topic + word count, format + layout, both speakers (source + file), both voices, model, motion/transitions, subtitles, look note, and the live cost estimate (one avatar clip per dialogue line, whole-second billing; +2 idle 4-s clips whenever the display type is Show Both; TTS per segment — free with BYO key; planning LLM). **Paid only — no free tier.** `get_shorz_credits` before offering "start now".

## Answer → execution map

| Step | MCP call |
|---|---|
| New project | `create_project { projectName, projectType: "podcast" }` |
| Q1/Q2 | `set_podcast_settings { podcastScript }` (strict tag format) |
| Q3 | `switch_project_aspect_ratio { aspectRatio }` |
| Q4 | `set_podcast_settings { podcastAvatarDisplayType: "Show Both Avatars"\|"Show Only Talking Avatar" }` — always write it explicitly |
| Q5 own file | `select_podcast_avatar_image { imageFilePath, role: "interviewer"\|"interviewee" }` |
| Q5 generate | `generate_images { description, referenceImages?, aspectRatio }` → poll → `select_podcast_avatar_image` |
| Q6 | `set_podcast_settings { podcastInterviewerVoice, podcastIntervieweeVoice }` |
| Q7 | `set_podcast_settings { podcastCameraMotion: "None"\|"Handheld Camera"\|"Slow Zoom", podcastTransitions }` |
| Q8 model | `set_avatar_settings { avatarModel }` |
| Q8 extras | `set_subtitle_settings` / `set_user_instructions` |
| Render | `trigger_create_video` → poll `get_video_generation_status` |

Notes: main VIDEO lane is disabled (footage → `broll`). A fresh project holds the legacy `podcast_avatar_display_type: "talking"`, which is **never normalized** — so despite its name it behaves as **Show Both Avatars** (split view, 2 idle clips billed), the opposite of what it reads like. Always write the display type explicitly. Speech volume rides `set_audio_settings { originalVolume }` (the "Main Video Volume" slider). Per-avatar crop keys exist only via `update_project_settings` (`podcast_interviewer_crop_x/_y`, `podcast_interviewee_crop_x/_y`, 0–100).
