# Single-asset edit tools (headless MCP)

Use these when the user wants **deterministic edits on local video or image files** — trim, crop, resize, letterbox, rotate, speed, volume, fades, audio extract/replace, concat, and probe metadata. One tool, `edit_image_with_ai`, is the exception — it calls GPT Image 2.5 and spends Shorz credits, everything else here is instant and free (FFmpeg/PIL only).

**Async exceptions:** `edit_image_with_ai` (paid GPT Image 2.5 call) and `remove_silence` (two-pass FFmpeg over possibly long talking-head footage) are **async by default**: they return `{ started, jobId }` immediately — poll `get_job_status { jobId }` until `lastStatus` is `completed` (`result` carries the usual `{ success, outputPath, summary }`, and `outputPaths` lists the file) or `error`. Pass `awaitCompletion: true` for the old blocking form on small files. Never re-call either tool because a poll seems slow — the job is still running (and `edit_image_with_ai` would bill again). All other tools in this family stay synchronous.

## Not a project type

These tools are **completely separate from Shorz project types**. They do **not**:

- require `create_project`, an open project, or `get_current_open_project`
- read or write `settings.json`, `ASSET_PATHS`, PromptBar, or panel settings
- run Create Video (`generate_video` / `trigger_create_video`) or use `projectType`

They only need **Shorz running** (Python backend via Electron) plus absolute file path(s) on disk. Most tools use **`inputPath`**; **`concat_media`** uses **`inputPaths`** (array, min 2); **`get_media_info`** returns metadata only (no output file).

Implementation mirrors `backend/core/Render/single_asset_tools.py` (same functions the **`auto-edit`** LLM pipeline uses internally), but MCP calls them **directly** — not through a project render.

Global routing and prerequisites: **`../../SKILL.md`** and **`../headless-workflows/README.md`**.

## When to use vs project workflows

| User goal | Use |
|---|---|
| Trim/crop/speed one file on disk | Single-asset MCP tools (this doc) — **no project** |
| LLM-driven edit with captions, B-roll, music, overlays | `auto-edit` **project** + **`trigger_create_video`** |
| Multiple shorts from one long video | `clipping` **project** |
| Transcript text only | **`transcribe_video_file`** |
| "What's in this video?" / pick a thumbnail moment | **`extract_video_frames`**, then read the returned frame image paths |

**Not exposed via MCP:** `analyze_video_and_edit`, `auto_edit_video`, `auto_clip_short_from_single_video` (LLM pipeline tools used inside projects).

## Tool contract

All tools share:

| Param | Required | Notes |
|---|---|---|
| `inputPath` | yes | Absolute path to a local video or image file |
| `outputPath` | no | If set, copies the rendered result here; otherwise returns a temp path under Shorz runtime |

**Returns:** `{ success, outputPath, summary, error }` — except **`get_media_info`** (`{ success, summary, mediaInfo, error }`) and **`extract_video_frames`** (`{ success, summary, frames, error }`, where `frames` is an array of `{ path, timestamp_sec }` image files), which return no single output file.

**Chaining:** Pass `outputPath` from step N as `inputPath` for step N+1. Call **`get_media_info`** first when you need duration or dimensions before trim/crop/resize. Its **`width`/`height` are DISPLAY dimensions** — a phone clip stored landscape with a 90°/270° rotation flag reports **portrait**, matching the frames that actually decode, so size math needs no rotation correction of your own. Each call re-encodes to a new file; the source is never overwritten unless you pass `outputPath` over the original (avoid that).

**Persistence:** Temp outputs live under runtime `Project_Files`. For durable assets, use **`save_file_as`** or **`import_frontend_assets`**. To use the result in a project later, import or patch `ASSET_PATHS` in a **separate** project workflow step.

## Available tools

| Tool | Purpose | Key params (besides `inputPath` / `outputPath`) |
|---|---|---|
| `trim_video` | Keep a time range | `startTimeSec`, `endTimeSec` |
| `remove_ranges` | Cut out one or more time ranges and keep the rest, in order (video or audio) | `ranges` — array of `[startSec, endSec]` pairs; overlapping pairs are merged, pairs past the end are clamped |
| `remove_audio` | Mute / strip audio | — |
| `set_audio_volume` | Volume multiplier | `volumeFactor` (0–10; 1 = original) |
| `change_video_speed` | Playback speed | `speedFactor` (e.g. 0.5, 2.0) |
| `set_image_duration` | Image → video duration | `durationSec` |
| `rotate_media` | Rotate 90° / 180° / 270° | `angleDegrees` |
| `flip_media` | Flip H/V/both | `direction`: `horizontal` \| `vertical` \| `both` |
| `reverse_video` | Play backwards | — |
| `loop_video` | Repeat clip | `numLoops` and/or `durationSec` |
| `fade_video` | Video fade in/out | `fadeInSec`, `fadeOutSec` |
| `freeze_frame` | Hold one frame | `timestampSec`, `freezeDurationSec` |
| `crop_media` | Pixel crop | `width`, `height`; optional `xCenter`, `yCenter` (0–1) |
| `audio_fade` | Audio fade in/out | `audioFadeInSec`, `audioFadeOutSec` |
| `remove_silence` | Cut dead-air pauses from talking-head footage (jump-cut tightening); **only call when the user explicitly asks** to remove silences/pauses/dead air or tighten pacing — never as part of general edits | `minSilenceSec` (default 0.5), `paddingSec` (default 0.15), optional `silenceThresholdDb` (auto-detected from the clip's own loudness if omitted) |
| `edit_image_with_ai` | Small, precise, localized AI edit via GPT Image 2.5 (style/color/lighting change, or a pointer/arrow/highlight/border near a subject) — a tweak, not a re-draw; **only call on explicit request**. **Spends Shorz credits**; image only | `instruction` (short, specific; max 500 chars) |
| `get_media_info` | Probe duration, size, fps, audio | — (no `outputPath`) |
| `extract_video_frames` | Save still frames as images (visual inspection / vision analysis); video only | `count` (1–60, default 5) **or** `timestamps` (seconds); optional `width`, `format` (`jpg` \| `png`) — returns `frames[]`, no `outputPath` |
| `resize_media` | Scale to width/height | `width` and/or `height` |
| `fit_to_aspect` | Letterbox/pillarbox to exact frame | `targetWidth`, `targetHeight`; optional `padColor` |
| `extract_audio` | Export audio from video | optional `format`: `aac` \| `mp3` \| `wav` |
| `replace_audio` | Swap video audio track | `audioPath` |
| `concat_media` | Join media in order — an **all-video** set or an **all-audio** set (e.g. re-joining TTS chunks into one narration track). Audio joins stream-copy when the inputs share container/codec/sample rate, otherwise re-encode. Mixing audio and video inputs is rejected | `inputPaths` (array, min 2) — no single `inputPath` |

## Execution sequence

1. Confirm **Shorz is running** (tools spawn the Python backend via Electron).
2. Verify the source exists: **`file_exists`** on `inputPath` (or every path in `inputPaths` for `concat_media`).
3. Optional: **`get_media_info`** to read duration and dimensions before trim/crop/resize.
4. Call the edit tool with explicit numeric params (do not guess trim times — ask the user if missing).
5. On success, use returned `outputPath` for the next edit or **`save_file_as`** to store the final file.
6. Each call is **synchronous and may take seconds to minutes** (MoviePy re-encode). Do not parallelize heavy edits on the same file.
7. **Optional:** If the user wants the file in a project, switch to the matching **`../project-workflows/`** doc and import or patch paths — do not conflate that with the edit step.

## Example chain (no project)

1. `get_media_info` — read duration/dimensions
2. `trim_video` — `inputPath: "C:/Videos/raw.mp4"`, `startTimeSec: 10`, `endTimeSec: 40`
3. `fit_to_aspect` — `inputPath: <trim outputPath>`, `targetWidth: 1080`, `targetHeight: 1920`
4. `save_file_as` — copy final `outputPath` to a user-chosen location

## Example: edit then use in a project

1. Headless: `trim_video` + `crop_media` on a disk file (this doc).
2. **Separate step:** User asks to add to an `auto-edit` project → `import_frontend_assets` with `assetType: "video"` and `overridePaths`, or patch `ASSET_PATHS` per **`../project-workflows/auto-edit.md`**.

## Common failures

- **File not found** — `inputPath` must be absolute and on disk before the call.
- **Unsupported format** — Video: `.mp4`, `.mov`, `.avi`, `.mkv`, `.wmv`, `.flv`, `.webm`. Image: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.webp`. Audio (`concat_media`, `replace_audio`): `.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`, `.flac`, `.opus`.
- **Shorz not running** — MCP bridge unavailable; start the desktop app.
- **Empty loop/fade args** — `loop_video`, `fade_video`, and `audio_fade` need at least one of their optional duration/loop params set.
- **`remove_silence` needs an audio track** — video-only, and the file must have audio to detect gaps in. It never runs unless the user explicitly asked for pause/silence removal.
- **`edit_image_with_ai` keeps edits small** — write the instruction as a short, specific, localized change ("add a red arrow at X"), not a full scene rewrite; the tool always wraps it in a preserve-everything-else prompt. On any API failure it falls back to the original image (reported as a success with an explanatory summary, not an error) — it never breaks the chain. Repeating the exact same instruction on the same image reuses a cached result at no extra cost. Accepts every image format listed above (`.webp` / `.bmp` / `.tiff` are re-encoded before upload); the image is sent to the model at up to 1536px on the long edge — a Shorz cap (GPT Image 2.5 itself accepts larger custom sizes), so feeding it a 4K source does not buy extra detail.
- **Resize requires a dimension** — `resize_media` needs at least one of `width` or `height`.
- **Concat cannot mix audio and video** — `concat_media` takes at least two paths that are **all video** or **all audio**; a mixed set is rejected with an explicit error. Images are not concatenable (use `set_image_duration` first).
- **Replace audio** — `replace_audio` needs a valid `audioPath` (.mp3, .wav, .m4a, .aac, etc.).
- **Wrong workflow** — Do not create an `auto-edit` project just to trim one file; use these tools instead.
