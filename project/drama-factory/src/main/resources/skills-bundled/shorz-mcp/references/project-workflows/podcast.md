# Podcast workflow (project type `podcast`)

Two-speaker interview / dialogue project. The script is a single block whose lines are tagged **`[Interviewer]`** / **`[Interviewee]`**; each speaker gets their own voice and an avatar image — **both avatar images are required** and the files must exist on disk (`render_generate_podcast.py` raises "Interviewer/Interviewee avatar is not set or does not exist" otherwise). Use **`set_podcast_settings`** for the panel contract. Global rules and routing live in **`../../SKILL.md`**.

Use this for **conversation / interview layouts**. For one character on camera, use **`avatar.md`** instead.

## What it looks like

The Podcast panel shows:

- A **single script field** with `[Interviewer]` / `[Interviewee]` line tags.
- **Two voices** — one per role (ElevenLabs).
- **Two avatars — BOTH REQUIRED** — image per role. The renderer **hard-fails before doing any work** if either avatar is unset or its file is missing, and the UI does **not** block Create Video on it — verify both paths with `file_exists` before triggering. Each can be generated in the in-app **Avatar Creator** from a text description, or from **up to 3 face reference photos** so the host keeps a specific person's exact face (headless equivalent: `generate_images` with `referenceImages`, then `select_podcast_avatar_image` / a path patch).
- **Display mode** — `Show Both Avatars` (split layout) or `Show Only Talking Avatar`.
- **Camera motion** — `None`, `Handheld Camera`, or `Slow Zoom`.
- **PromptBar** — optional B-roll / music / SFX guidance. **Not** the dialogue.

Create Video renders the conversation with each speaker's voice and image, switching attention according to the display mode.

**Main VIDEO (“Import Main Assets”)** — **`podcast`** projects **do not** expose the timeline main VIDEO lane in the Electron UI (**SKILL.md** → *Main VIDEO import*). **`import_frontend_assets`** with **`assetType: "video"`** is **rejected with an error** here (headless `overridePaths` path). Use **`assetType: "avatar"`** or **`"image"`** + **`select_podcast_avatar_image`** (or MCP path patches on podcast avatar keys) instead.

## Tool contract

**Primary tool:** `set_podcast_settings`

**Arguments:** `projectPath` (absolute) and a `settings` object with only the keys you want to change.

**Supported keys in `settings`:**

| Key | Type | Notes / validation |
|---|---|---|
| `podcastScript` | string | Max **20000** chars and **2000** words. Each non-empty line must look like **`[Interviewer] Your line`** or **`[Interviewee] Your line`**: `[Interviewer]` / `[Interviewee]` are matched **case-insensitively** by MCP validation, tags must contain no inner spaces (e.g. not `[Interview er]`), **at least one space is required immediately after `]`**, and the remainder must include at least one non-whitespace token. Include at least one line per role. |
| `podcastInterviewerVoice` | string | Non-empty; ElevenLabs voice id/name. |
| `podcastIntervieweeVoice` | string | Same. |
| `podcastInterviewerAvatar` | string or `null` | Path/URL to interviewer avatar image. |
| `podcastIntervieweeAvatar` | string or `null` | Path/URL to interviewee avatar image. |
| `podcastAvatarDisplayType` | string enum | **`Show Both Avatars`** \| **`Show Only Talking Avatar`** (verbatim). |
| `podcastCameraMotion` | string enum | `None` \| `Handheld Camera` \| `Slow Zoom`. |
| `podcastTransitions` | array of strings | Optional. Light-leak overlays played over each **speaker change**: `Transition01` … `Transition20`, or `[\"None\"]` (default). One is drawn at random per cut, never repeating back-to-back; each carries its own whoosh mixed at the project's Sound Effects volume. Unknown ids → rejected. **Only applies when `podcastAvatarDisplayType` is `Show Only Talking Avatar`** (or the project is square) — the split view keeps both avatars on screen and never cuts. |

`podcastAvatarDisplayType` is the user-facing string — older project files on disk may contain a legacy value like `talking`; the MCP and current UI use **only** the two values above. Resend with the verbatim string if validation rejects the legacy value.

**Persistence oracle** — confirm via `read_project_settings` → `PODCAST_INTERVIEW`:

| MCP key | `PODCAST_INTERVIEW` key |
|---|---|
| `podcastScript` | `podcast_script` |
| `podcastInterviewerVoice` | `podcast_interviewer_voice` |
| `podcastIntervieweeVoice` | `podcast_interviewee_voice` |
| `podcastInterviewerAvatar` | `podcast_interviewer_avatar` |
| `podcastIntervieweeAvatar` | `podcast_interviewee_avatar` |
| `podcastAvatarDisplayType` | `podcast_avatar_display_type` |
| `podcastCameraMotion` | `podcast_camera_motion_type` |
| `podcastTransitions` | `podcast_transitions` (JSON array string) |

### Interviewer / interviewee avatars (local image files)

| MCP tool | Arguments | Effect |
|---|---|---|
| `select_podcast_avatar_image` | `projectPath`, `imageFilePath`, `role`: `interviewer` \| `interviewee` | Reads a local image, saves it into the project, and updates `podcastInterviewerAvatar` or `podcastIntervieweeAvatar`. Equivalent to patching that key via `set_podcast_settings` with a file path. |

**Supported image extensions:** `.png`, `.jpg`, `.jpeg`, `.webp`.

Alternative: `import_frontend_assets` with `assetType: "avatar"` or `"image"`, then patch the returned path via `set_podcast_settings`.

**Generate a host from a face photo** — to create a host image that must look like a **specific person**, call `generate_images` with up to **3** `referenceImages` (face photos as local paths / http(s) / data / `local-resource://` URLs). The same face/identity is preserved and `description` is treated as the scene (pose/clothing/lighting/background), not the face. Save the returned path onto the role with `select_podcast_avatar_image` or a `set_podcast_settings` path patch. This mirrors the Avatar Creator modal's **"Face reference photos (optional)"** picker (shared by Avatar and Podcast projects).

Voice discovery: `list_elevenlabs_voices`.

### PromptBar vs dialogue

For project type `podcast`, the **PromptBar** (`set_user_instructions` → `UI_SETTINGS.user_input_instructions`) is **optional B-roll / music / SFX guidance**. **The dialogue itself goes in `podcastScript`** with `[Interviewer]` / `[Interviewee]` tags. Never overwrite PromptBar with the script. Never put aspect ratio or pixel dimensions in PromptBar (**SKILL.md** → *Output framing*).

**Imported music works here too.** Import any number of tracks (`import_frontend_assets` with `assetType: "music"`, free) and the PromptBar can arrange them — play order, a section of one named track, where the music starts/ends on the timeline, volume, fade in/out, and mix-vs-replace. Full vocabulary: **`auto-edit.md`** → *Imported music*. Typical podcast ask: *"use my track only over the first 15 seconds as an intro bed at 30%, nothing under the rest of the conversation."* Beat-synced **cutting** does **not** apply here (multi-asset `auto-edit` only).

## Instruction handling rules

- **Create podcast output** — set the script (with role tags), both voices, **both avatars (required)**, display mode, camera motion. Persist PromptBar only if the user asked for B-roll / music / SFX guidance.
- **Edit dialogue only** — patch only `podcastScript`. Validate role-tag format before sending.
- **Change voices only** — patch `podcastInterviewerVoice` and/or `podcastIntervieweeVoice`.
- **Change framing only** — patch `podcastAvatarDisplayType` and/or `podcastCameraMotion`.
- **Change avatars only** — use `select_podcast_avatar_image` (local files) or patch `podcastInterviewerAvatar` / `podcastIntervieweeAvatar` directly.
- **Configure only** — patch settings without triggering Create Video.
- **Minimal patches** — pass only requested keys.

## Execution sequence

1. **Resolve project** per **SKILL.md** → *Project targeting rules*. Create only with explicit approval via `create_project` with `projectType: "podcast"`.
2. **Read state** (optional): `read_project_settings` → inspect `PODCAST_INTERVIEW`.
3. **Voices** — `list_elevenlabs_voices` if unknown, then patch `podcastInterviewerVoice` / `podcastIntervieweeVoice`.
4. **Avatars** — `select_podcast_avatar_image` per role (local paths) or `import_frontend_assets` + path patch.
5. **Script** — patch `podcastScript`. Follow the table rules (space after `]`; MCP tags are case-insensitive); script must include at least one non-empty line per role.
6. **Display and motion** — patch `podcastAvatarDisplayType` and `podcastCameraMotion` as requested.
7. **PromptBar (optional)** — `set_user_instructions` only for B-roll / music / SFX guidance.
8. **Create Video** (only on user request):
   - `trigger_create_video` (preferred) or `generate_video`.
   - Poll **`get_video_generation_status`** until terminal. `fetch_app_events` only on request or when debugging.
   - `stop_video_generation` on user request.
9. **Return outcome** — generation success/failure, output paths, validation errors.

## Quick defaults

- `podcastInterviewerVoice`: `callum` when the Shorz UI initializes the panel state; `Alice` on a brand-new project that has never been opened (the disk template in `defaultProjectSettings`).
- `podcastIntervieweeVoice`: `lily` (UI initial state) / `Clyde` (disk template, freshly created).
- `podcastAvatarDisplayType`: `Show Both Avatars`
- `podcastCameraMotion`: `None`
- `podcastScript`: `""`

Always confirm the current values via `read_project_settings` → `PODCAST_INTERVIEW.podcast_interviewer_voice` / `podcast_interviewee_voice` rather than assuming a particular default.

## Common failures

- **A dialogue line longer than the model window** — the podcast renderer never splits a line (unlike the avatar flow, which auto-splits at silence). A line past ~29 s on OmniHuman 1.5 or ~60 s on either Kling model fails, and the render degrades silently: a looped idle clip with no lip-sync in split view, or a **black frame with audio** in `Show Only Talking Avatar`. Keep lines under ~60 words (OmniHuman) / ~140 words (Kling).
- **Idle clips are billed on display type alone** — `Show Both Avatars` always generates 2 idle clips (~4 s each), including on a **1:1 project**, which renders fullscreen and never shows them.
- **Avatar Model lives elsewhere** — `Kling Avatar` / `Kling Avatar Pro` / `OmniHuman 1.5` is the largest cost lever and is set via **`set_avatar_settings { avatarModel }`**, NOT `set_podcast_settings`.
- **Fresh projects ship legacy `talking`** in `podcast_avatar_display_type`, never normalized — it behaves as **Show Both Avatars**, the opposite of its name. Always write the display type explicitly.
- **Script too short** — the renderer requires **more than 10** characters after trimming (`len(script.strip()) <= 10` fails, so 10 is rejected and 11 is the first accepted length).

- **Role-tag format errors** — Common fixes: preserve tags as `[Interviewer]` / `[Interviewee]` (**no spaces inside brackets**); **never glue text to `]`** (e.g. `[Interviewer]Hello` fails — use `[Interviewer] Hello`). MCP matches tag spelling case-insensitively even though the shipped UI prefers title case.
- **Missing role coverage** — Script must contain at least one line for each speaker.
- **Invalid display / camera enum** — Resend with the verbatim values listed above (e.g. `Show Both Avatars`, not legacy `talking`).
- **Script accidentally placed in PromptBar** — Move dialogue to `podcastScript`; clear or rewrite PromptBar via `set_user_instructions`.
- **Voice not recognized** — Pick one from `list_elevenlabs_voices` before patching.
- **Avatar path wrong** — Resend with a valid local path (allowed extensions) or import first.
