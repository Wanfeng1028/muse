# Guided Project Creation (wizard flows)

This folder turns a **vague video idea** into a fully-specified Shorz project through a short, option-driven Q&A — then (only on explicit confirmation) executes the matching `references/project-workflows/*.md` flow.

## When to run a guided flow

Run the wizard when the user expresses **intent to make a video but has not supplied the concrete inputs** the project type needs — no file path / URL, no format, no counts, no script, etc. Examples: "i want to clip a youtube video", "make me a talking avatar video", "I want an ad for my product", "turn this idea into a video".

Do **NOT** run the wizard when:
- The user already gave a complete or near-complete spec (URL + "3 vertical clips with subtitles" → just confirm the remaining gaps in ONE question, or proceed).
- The user asks for a direct edit on an existing project ("change the subtitles to yellow") — use the panel workflow.
- Another skill is driving (e.g. `shorz-create-video-research-recap` has its own pipeline).
- The user explicitly says "just do it / use defaults" — apply the per-type recommended defaults, show the summary, and go straight to the confirmation question.

Anything the user DID already specify is **locked in** — never re-ask it. Skip that wizard step and show the value in the final summary.

## Type router (project flows)

| User intent sounds like | `projectType` | Guided flow file |
|---|---|---|
| "clip / cut a long video into shorts", "clip this youtube video" | `clipping` | `clipping.md` |
| "edit my footage / clips into a video", "montage", "vlog edit" | `auto-edit` | `auto-edit.md` |
| "make a video about X", "turn this script/idea into a video", "faceless video" | `text-to-video` | `text-to-video.md` |
| "talking head", "AI presenter/spokesperson", "avatar video" | `avatar` | `avatar.md` |
| "podcast video", "two people talking", "interview video" | `podcast` | `podcast.md` |
| "ad / advertisement / promo for my product" | `advertisement` | `advertisement.md` |
| "music video for my song", "visualize this track", "AI visuals for my single" | `music-video` | `music-video.md` |

If the type is ambiguous, ask ONE routing question first (≤4 grouped options + the automatic custom input), e.g.:
1. **Clip or edit footage I already have** (Clipping / Auto Edit)
2. **Generate a video from an idea, a script or a song** (Text-to-Video / Music Video)
3. **AI presenter** — one host (Avatar) or two-person dialogue (Podcast)
4. **Product advertisement** (Advertisement)

then, if the pick still spans two types, ask one follow-up to split them.

## Asset router (modal flows — no `projectType`)

Two guided flows produce a **single asset**, not a project. They never call `create_project` and have no Create Video step, so the confirmation contract adapts: the final question is "generate it now?" rather than "start a project?".

| User intent sounds like | Flow file |
|---|---|
| "make a thumbnail", "YouTube cover image", "a clickable thumbnail" | `thumbnail-creator.md` |
| "animated intro/outro", "logo reveal", "kinetic text", "title card", "animated chart", "standalone motion graphics" | `animation-studio.md` |

**Routing note — animation vs motion-graphics overlay.** If the graphics go **on top of existing footage** (chroma-keyed lower thirds, callouts over a talking head), the **`shorz-motion-graphics`** companion skill owns that end to end — source analysis, safe zones, the chroma-key constraint block and the ffmpeg composite. Load it instead. Use `animation-studio.md` when the animation **is** the deliverable (standalone clip, intro, title card) or when there is no footage to composite onto yet.

## How to ask (question protocol)

- **Use the interactive question tool** (`AskUserQuestion`) when the client provides it — this is what makes the wizard feel native in the Claude Desktop app. Fall back to plain-text numbered options otherwise.
- **≤4 preset options per question.** The UI adds a free-text "Other" automatically — never add your own "Other/custom" option. In plain-text fallback, explicitly add "…or type your own".
- **Recommended default goes FIRST**, labeled `(Recommended)`. The recommendation must fit what is already known (e.g. vertical first for clipping; if the user said "for YouTube longform", recommend horizontal instead).
- **One dependent step at a time.** Batch up to 4 questions in one call ONLY when they are independent of each other's answers. Branching steps (anything marked IF/THEN in the flow files) must wait for the previous answer.
- **Ground every option in the app.** Options, ranges and defaults come from the per-type flow file (which mirrors the real panels). Never offer a value the app cannot persist. Free-text answers get clamped/validated to the documented range — tell the user when you clamp ("max is 8, so I set 8").
- **Widget steps (mandatory where available).** Image-slot, model and voice choices render as inline cards (`widgets.md`) whenever the client has a `show_widget` tool — search for it with `ToolSearch` first, it is usually deferred. On those steps you render the cards and **wait**; you never open the native file dialog or write the setting until the card's button phrase arrives as the user's message. Every other step, and every client without `show_widget`, uses the question tool exactly as written.
- Keep each flow to its listed steps (~4–7 questions). Optional extras live behind a single "anything else?" step, not more questions.

## Question design rules (learned the hard way — apply to every flow)

These are the recurring failure modes, every one of them found in a real draft of these flows. Check a flow against all eleven before running it.

1. **Aspect ratio before any AI image generation.** The Avatar Creator, the podcast speaker generator and the advertisement and music video character generators all size their output from the *project* ratio. Ask the format question before any step that generates an image, or you hand the user a portrait built for the wrong frame.
2. **Content before cost levers.** Anything that multiplies cost — scene count, clip count, avatar angles, a per-second video model — must be asked *after* we know how much content there is. Recommending "AI video clips" before seeing the script is a blind recommendation: the same option is cheap for a 30-second script and enormous for a 5-minute one. State the real implication at the moment of choosing — and make sure it is the one that actually dominates (see rule 9).
3. **Never offer an option a prior answer made impossible.** A product-only ad has no character who can speak to camera; a photos-only slideshow has no speech to caption; split-view podcasts never cut, so transitions do nothing. Suppress the option instead of letting the user pick a no-op — and skip the whole question when every option would be one.
4. **Recommendations adapt to known facts.** We probe `get_media_info` and we can count script sentences, so the default must move with them. Three clips is timid for a 90-minute podcast and aggressive for a 4-minute video. A static "(Recommended)" that ignores what we already know is a bug, not a default.
5. **Ask what the video is about.** Every flow must capture the user's creative intent somewhere — not only mechanical settings. An auto-edit brief reading "fast and punchy, ~60 s, hard cuts" throws away the thing they actually came to make.
6. **Word options in the terms the user just chose.** After they pick 16:9, "both speakers side-by-side" beats the abstract "split layout". Reuse their format, platform and subject words in the option labels.
7. **Validate combinations, not just values.** Each answer can be individually legal and jointly impossible — 8 clips × 90 s cannot come out of a 5-minute source. Check the product of the answers against the real constraint before showing the summary.
8. **Never surface an internal mechanic as a user-facing limit — but check per flow whether it really is internal.** The test is always: **does this change what the user can get, what they pay, or what they see?** The same constant can fail that test in one flow and pass it in another. The avatar renderer auto-splits a long script at silence and stitches it, so "OmniHuman — 29 s clip cap" is noise there; it reads as *"my video can only be 29 seconds"* and is simply wrong. The **podcast** renderer never splits a dialogue line, so the identical constant becomes a hard per-line limit: an over-long line fails and silently degrades to a looped idle clip or a black frame. Never assume a cap is handled automatically — find the code that handles it, or state it as the real limit it is.
9. **Verify a claimed consequence before stating it.** "Angles multiply the bill" sounds plausible and is wrong: billing is per second of output, so the same script costs about the same either way — angles really add three one-time image generations plus about half a second of whole-second rounding per sentence. A wrong reason steers the user to the wrong choice just as badly as a wrong option. Do the arithmetic, then describe the effect that actually dominates (here: a look decision, not a budget one).
10. **Say only what the code says.** Latency claims, quality claims and drift claims are usually unverifiable from source — either cut them or mark them as expectations rather than facts. Where a real mechanism exists, cite the mechanism instead: "each scene is an independent generation, so a voice is not guaranteed to stay consistent" is defensible; "the voice drifts" is not.
11. **Check both directions of a silent failure.** For every option, ask what happens when it goes wrong: does the render abort, degrade, or silently drop content? The three demand different wording. A paid feature at zero balance *degrades* (the video still renders, minus that feature). A failed text-to-video clip *falls back to a still*. An exhausted ad quota *shortens the ad*. An over-long podcast line *becomes a black frame*. None of these error out, so the wizard must warn up front and check the delivered output afterwards.

## Summary + confirmation contract (every flow ends with this)

1. Print a **readable summary** of the video (or asset) about to be created — a short markdown table or list: project type, source/inputs, format, every chosen setting, anything intentionally left on defaults, and a cost note (free-tier eligible vs paid; name the paid features chosen).
2. Then ask the **start question** with exactly these options:
   1. **Yes — start now in a new project** `(Recommended)`
   2. **Yes — start in an existing project** → then resolve via `list_projects` and ask which one (project names as options; if the chosen project's `projectType` differs, follow SKILL.md *Project targeting rules* rule 4 — never silently repurpose)
   3. **Configure only — set everything up but don't render** → create/patch the project and stop before `trigger_create_video`
   4. **No, not yet**
3. On **"No, not yet"**: do nothing. The summary stays in chat; if the user comes back with "ok start", execute it as-is without re-asking.

**Asset flows** (`thumbnail-creator.md`, `animation-studio.md`) replace step 2 with: 1. **Yes — generate it now** `(Recommended)` · 2. Change something first · 3. No, not yet.

## Execution contract (after "Yes")

1. `get_shorz_credits` first. Paid-only types (`text-to-video`, `avatar`, `podcast`, `advertisement`, `music-video`) need balance; `auto-edit`/`clipping` may ride the free tier — follow SKILL.md free-tier rules (pin the free model, honour the source cap). Both asset flows are paid.
2. `create_project` with the flow's `projectType` (or resolve the chosen existing project). Asset flows skip this.
3. Apply the answers via the mapping table at the bottom of the flow file (each answer → one MCP call/patch). Follow the matching `references/project-workflows/*.md` (or panel workflow) for tool semantics — the wizard decides *what*, the workflow file defines *how*.
4. Import/download assets (async where documented — poll the documented status tool).
5. `trigger_create_video` / `generate_video`, then poll `get_video_generation_status` to terminal and report the outcome honestly.

## Flow files

| File | Covers |
|---|---|
| `clipping.md` | Source (URL/local) → format → clip count → max length → subtitles → focus |
| `auto-edit.md` | Footage → what it's about → format → extras → style → cleanup → motion → subtitles → polish |
| `text-to-video.md` | Script → source media (3-way IF/THEN) → format → models → references → motion → extras |
| `avatar.md` | Format → presenter → script/voice → angles → model → extras |
| `podcast.md` | Dialogue → format → display type → speakers → voices → motion → quality |
| `advertisement.md` | Mode → format → images → length → tone → delivery → extras |
| `music-video.md` | Song → whole song or a part → format → concept → artist → models → pace + finishing |
| `thumbnail-creator.md` | Format → subject → text → references → model → variations |
| `animation-studio.md` | Kind → style → imports → output format → model |
| `widgets.md` | Card-widget templates + fixed button phrases for image / model / voice steps |
