# Guided flow — CLIPPING

One long source video → 1–8 standalone short clips, chosen by AI from the transcript. Follow the shared protocol in `README.md`. Tool semantics: `references/project-workflows/clipping.md`.

**Route here when:** "clip this youtube video", podcast/stream/webinar → shorts, "best moments", "highlights", "N clips from X".
**Route away:** one montage from many files / filler-word or silence removal → `auto-edit`; no source video at all → `text-to-video` (or `music-video` when the input is a song). Clipping picks time ranges only, and the source must contain audible speech.

## Question sequence

### Q1 — Source video (mandatory; never proceed without it)
"Where is the video you want to clip?"
1. **Paste a link — YouTube, TikTok, Facebook or Instagram** (Recommended)
2. A file on my computer (give me the path)
3. The video already in an existing project

- Only those **four** platforms are downloadable — **X/Twitter and other sites are NOT supported**; the user must download such files themselves and give a local path.
- If the user already pasted a URL or path, this step is answered — validate it and move on.
- Local path → imported then **overwritten as a single string** into `ASSET_PATHS.main_video_asset_paths` (MCP import appends; clipping requires **exactly one** main video or the render aborts).
- **Probe `get_media_info` before Q2** — the duration sets the Q3 recommendation and the Q4 feasibility check, and the orientation informs the format advice. Free-tier users with sources > 30 min must be told the run will bill instead of being free.
- **The MCP path never measures source length** — the free-run duration check only runs in the UI, so probe it yourself and honour the cap.
- **No audible speech = no clipping.** Selection runs off the transcript, so a music-only or silent source cannot be clipped at all; say so and stop rather than burning a render.

### Q2 — Target format (default vertical)
"Which platforms/format are these clips for?"
1. **Vertical 9:16 — TikTok / Reels / Shorts** (Recommended; also the app default)
2. Horizontal 16:9 — YouTube / landscape
3. Square 1:1 — Instagram feed

Maps to `switch_project_aspect_ratio` (`9:16` 1080×1920 / `16:9` 1920×1080 / `1:1` 1080×1080). These three are the only ratios the app supports. If the probe showed the source is already vertical, say 9:16 keeps the full frame; if landscape, note that vertical crops in on the subject.

### Q3 — Clip count (limit 1–8; adapt the recommendation to the source length)
"How many clips should it create? (1–8)"

**Lead with the count the source can actually support**, using the probed duration — a static "3" is timid for a 90-minute podcast and aggressive for a 4-minute video:

| Source length | Recommend first | Then offer |
|---|---|---|
| under ~5 min | **1–2** | 3, and note that more would slice the same material thin |
| ~5–20 min | **3** | 1, 5, 8 |
| ~20–60 min | **5** | 3, 8, 1 |
| over ~60 min | **8** | 5, 3, 1 |

**Clip count is a real cost lever, not a free knob.** The whole effects chain runs **once per exported clip**, and the word-level transcript is rebuilt on every pass — so with subtitles enabled (which Q5 recommends) N clips means N word-level transcriptions plus N× every transcript-analysis LLM call. The in-app estimate bar does *not* include this and says so in its own footnote. Tell the user that doubling the clip count roughly doubles the per-clip effects work.

Custom input: values outside 1–8 are **silently clamped on write** (non-numeric becomes `1`) rather than rejected — so clamp deliberately and say what you set. Maps to `update_project_settings → { CLIPING: { clipping_num_clips: "<n>" } }` (string value; note the app's `CLIPING` spelling).

### Q4 — Maximum clip length (no hard setting — becomes PromptBar text)
"How long should each clip be, at most?"
1. **Let the AI decide — typically 15–90 s** (Recommended; adds nothing to the prompt)
2. Short hooks — max ~20–30 s each
3. Under 60 s each (platform-safe shorts)
4. Longer highlights — 60–90 s each

Custom input in **seconds**. There is no length setting anywhere in the app — the choice becomes a sentence in the creative brief. Absurdly short asks are pointless rather than cleanly rejected: a sub-0.5 s range is only refused when it starts within half a second of t=0, because the planner pads every segment with a ~0.5 s lead-in first. Refuse them in conversation instead of relying on a backend error.

**Validate the combination, not just the values.** Ranges past the end of the source are **clamped, not rejected**, so an over-ambitious ask degrades rather than failing cleanly. Asking for 8 × 90 s out of a 5-minute source ends one of two ways: the model quietly shrinks the clips and ignores your max-length sentence, or it emits overlapping ranges and **the entire run aborts with no output at all** (non-overlap is hard-verified with a 0.15 s tolerance, a wrong clip count is likewise rejected, and there is exactly one model attempt — no retry). When `count × max length` doesn't sit comfortably inside the probed duration — ideally under about half of it, since the best moments are never back-to-back — say the arithmetic out loud and offer the achievable combination.

### Q5 — Subtitles (fully available for clipping; applied to every clip)
"Burned-in captions on the clips?"
1. **Yes — auto subtitles, style tuned for the format** (Recommended for 9:16 short-form)
2. Yes — subtitles + a title/hook card on each clip
3. No captions
4. Keep the project's current text settings

Maps to `set_subtitle_settings` (+ `set_title_settings` for option 2). For option 1 pick a legible short-form default (centered, large, high-contrast) per `references/panel-workflows/subtitle.md`.

### Q6 — What to clip (optional; free-text last)
"What should the clips focus on?"
1. **Automatic — the most engaging moments** (Recommended; pass `userInstructionsOverride: ""` ONLY if Q4 also chose "AI decides" — a Q4 length cap must still reach the brief)
2. Funniest / highest-energy moments
3. One clear tip or takeaway per clip
4. A specific topic, quote, or time range (they describe it)

Merge Q4 + Q6 into ONE brief and persist with `set_user_instructions` (never include aspect/pixel tokens). With ≥2 clips, phrase it as "N distinct moments spread across the video".

## Summary + confirm

Per `README.md` contract. Include: source, format, clip count, max length, subtitles, focus brief, model, and an honest cost line. Clipping is **free-tier eligible** (allowance and 30-min source cap are server-driven; the free model id comes off the free-run payload — currently `google/gemini-3.8-flash` — so read it rather than hardcoding it). On credits: one STT pass over the source + one clip-selection LLM call, **plus the per-clip effects chain multiplied by the clip count** (see Q3). The cutting itself is free; the effects on each clip are not.

## Answer → execution map

| Step | MCP call |
|---|---|
| New project | `create_project { projectName, projectType: "clipping" }` — it does NOT validate the name (only rename/duplicate do), so apply the rules yourself: ≤120 chars, no `< > : " / \ | ? *`, no trailing space or period, not a Windows reserved stem (CON, PRN, AUX, NUL, COM1-9, LPT1-9) |
| Q1 link | `download_social_video { url, platform: "auto" }` → poll `get_social_video_download_status` → returned `localFilePath` |
| Q1 local file | `import_frontend_assets { assetType: "video", overridePaths: [path] }` |
| Q1 (both) | then **overwrite** `ASSET_PATHS.main_video_asset_paths` with the ONE path (string), verify `file_exists` |
| Q2 | `switch_project_aspect_ratio { aspectRatio }` (skip if already correct) |
| Q3 | `update_project_settings { updates: { CLIPING: { clipping_num_clips: "<n>" } } }` |
| Q4+Q6 | `set_user_instructions` (or `userInstructionsOverride` on trigger; `""` for fully automatic) |
| Q5 | `set_subtitle_settings` / `set_title_settings` |
| Free tier | pass the free model id on `trigger_create_video { mainAiModelName }` — the MCP path does NOT pin it for you |
| Render | `trigger_create_video` → poll `get_video_generation_status` to terminal; expect **N separate output files** |

Pre-flight: exactly one existing main video; count on disk; `VIDEO_SIZE` matches Q2. Imported music restarts in **every** clip (the chain runs once per clip). If the plan comes back invalid (overlapping ranges or wrong clip count) the run ends as `completed_no_output` with **no partial clips and no retry** — report that as a failed plan, not a rendering bug.
