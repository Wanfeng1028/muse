---
name: imageat-explainer-video
description: Make a finished narrated explainer video (editorial collage or paper-diorama documentary look) end to end with imageat — topic research, fact-checked script, style-locked clips, one narrator voice, burned subtitles and a single assembled mp4. Use when the user asks for an explainer video, a motion-graphics or "Vox-style" video, a faceless narrated short or YouTube video, a data story, "make a video about X", or a video about something trending, even when no topic is given.
---

# imageat explainer video

One request in, one finished mp4 out: a narrated explainer built from editorial
collage or paper-diorama clips, one documentary narrator, tight factual writing
and burned subtitles. Every generation runs on the user's imageat account.

## Tools

With the imageat MCP server connected (https://mcp.imageat.com/mcp), use:

| Step | MCP tool | REST equivalent (`https://imageat.com/api/v1`) |
|---|---|---|
| Style key (only if not using a hosted one) | `imageat_generate_image` | `POST /images` |
| Clips | `imageat_generate_video` | `POST /videos` |
| Poll clips and the final video | `imageat_check_video_status` | `GET /videos/status?taskId=` |
| Voices | `imageat_list_voices` | `GET /audio/voices` |
| Voiceover | `imageat_generate_speech` | `POST /audio/speech` |
| Assembly | `imageat_assemble_video` | `POST /videos/assemble` |
| Balance | `imageat_check_credits` | `GET /credits` |

REST callers send `Authorization: Bearer $IMAGEAT_API_KEY` (keys from
https://imageat.com/projects/keys). Use web search and fetch for research.

## Operating mode

Run hands-off. The user is delegating the whole job.

- Honor anything the user specified (topic, angle, length, style, voice, aspect).
  Decide everything else with the defaults below.
- Before the first paid call, post one short plan: topic and angle, style, block
  count, voice, and estimated credits. Then continue without waiting, unless the
  user asked to approve first or the estimate is more than their balance
  (`imageat_check_credits`).
- Never stop mid-pipeline for a question a default answers. Loose clips are not a
  deliverable; the job ends with one assembled mp4.

## Defaults

| Setting | Default | Change when |
|---|---|---|
| Style | Collage (below) | Topic is geopolitics, money, power, or the user wants "cinematic" → Diorama |
| Aspect | 9:16 | User says YouTube or landscape → 16:9 |
| Length | 1 minute = 6 blocks of 10s | User gives a length (1–10 minutes, 6 blocks per minute) |
| Clip model | `gemini-omni`, 10s, 720p | User wants it cheaper → `wan3` at 480p |
| Voice | `elevenlabs-tts`, voice `Brian` | User names a voice or language |
| Subtitles | On, bottom | User says no subtitles |
| Language | English narration | User asks for another; prompts stay in English |

Cost per minute: about 441 credits with `gemini-omni` (70 per clip), about
141 with `wan3` 480p (20 per clip). Voice takes are 3 credits each and
assembly is 3 credits per minute with subtitles.

## Story rules

Pretty, unrelated scenes play like a slideshow. What holds attention:

- **One recurring object.** Pick a physical metaphor (a fuse, a ship, a coin, a
  thread) that appears in every block and changes as the story escalates.
- **One question.** Block 1 asks it or states the surprising fact; the last block
  answers it and reframes the opening.
- **Every block earns its place** with a number, a date, a place or a comparison.
- **Show the line.** Each clip literally illustrates its own narration line.

## Pipeline

### 1. Topic

Topic given: use it. No topic: search for what is trending this week, then pick a
subject with a why/how question at its core, at least one surprising number,
strong visual potential (maps, charts, objects) and broad appeal. Skip active
tragedies, gossip without a data angle, and anything you cannot confirm with two
independent sources. Name one runner-up in the plan message.

### 2. Research

Never script from memory. Read the two or three best sources and collect the hook
statistic, three to five concrete facts, and the counterintuitive turn.
Cross-check every number against a second source and keep a Sources list.
A vague true line beats a specific false one; never invent quotes or figures.

### 3. Script

Write N blocks, one per 10s clip, each **18–22 words** of plain spoken text:
no stage directions, numbers spelled out ("seventy percent", "twenty twenty-one").

- Block 1, cold open: the most surprising fact or question, stated flat. No greeting.
- Block 2, stakes: why it matters to the viewer.
- Middle blocks, evidence: one idea each, escalating, each anchored to a fact.
- Second-to-last, the turn: the "but here is the thing".
- Last block, the answer plus a closing line that reframes the opening.

Tone: curious, precise, a little dry. The narrator explains and never hypes.
Prefer one flowing sentence per block: narrators pause at every full stop, so a
choppy line runs longer than its word count suggests.

### 4. Style key

Use a hosted key and skip this step's cost:

| Style | 9:16 | 16:9 |
|---|---|---|
| Collage | https://cdn.imageat.com/explainer/style-keys/collage-9x16.jpg | https://cdn.imageat.com/explainer/style-keys/collage-16x9.jpg |
| Diorama | https://cdn.imageat.com/explainer/style-keys/diorama-9x16.jpg | https://cdn.imageat.com/explainer/style-keys/diorama-16x9.jpg |

For a custom look, generate one with `imageat_generate_image` (`nano-banana-pro`,
the target aspect ratio) from the style's SWATCH prompt below, and use its URL.
The same key goes on every clip of the video.

### 5. Clips

One `imageat_generate_video` call per block:

```json
{
  "model": "gemini-omni",
  "prompt": "<block prompt>",
  "referenceImageUrls": ["<style key URL>"],
  "aspectRatio": "9:16",
  "duration": "10s",
  "resolution": "720p"
}
```

Budget runs use `"model": "wan3", "resolution": "480p"` with the same fields.
Always pass `aspectRatio` explicitly. Submit every block, record each task ID
against its block number, and poll `imageat_check_video_status` every 30–60 seconds.
Re-submit only failed or off-style blocks.

Write each prompt as four labeled lines:

```
STYLE: <the style's STYLE line>
SHOT: <what appears, in order, illustrating this block's narration>
MOTION: <entrances, camera move, pacing>
NEGATIVE: <the style's NEGATIVE line>
```

### 6. Voiceover

Pick one voice for the whole video (`imageat_list_voices`; default `Brian`, or
`George`, `Daniel` and `Bill` for a documentary feel). One
`imageat_generate_speech` call per block, with the block's exact line.

Each result has `durationSec`. Every take must be at most the clip length plus
0.3s (10.3s for a 10s clip); aim for 7.5–9.5s. If a take runs long, shorten the
line by a few words and re-voice that block only. If one is under 6s, the block
will feel empty: add a clause and re-voice.

### 7. Assemble

As soon as every clip and take is done, in the same run:

```json
{
  "items": [
    { "videoUrl": "<clip 1 mp4>", "audioUrl": "<take 1 url>", "text": "<block 1 line>" },
    { "videoUrl": "<clip 2 mp4>", "audioUrl": "<take 2 url>", "text": "<block 2 line>" }
  ],
  "subtitles": true,
  "subtitlePosition": "bottom"
}
```

Items play in order; block N's take always plays over clip N, starting 0.3s in.
Every file is measured before any charge: an error lists exactly which blocks run
long, so fix those and call again. The result is a task ID; poll
`imageat_check_video_status` with it (about a minute) for the final mp4.

## Style: Collage

A motion-designed magazine spread, never a filmed scene. Best for data stories,
"why X" questions, money and tech. Subtitles carry all words; clips have none.

- **STYLE:** editorial mixed-media collage matching the reference image exactly: flat mustard-yellow paper background with halftone dots, black-and-white archival photo cutouts with torn white paper borders, masking tape strips, flat navy and coral shapes, hand-drawn black marker strokes, soft drop shadows.
- **NEGATIVE:** no readable text, no letters, no numbers, no logos, not photorealistic, no live action, no 3D render.
- **Devices to combine (two or three per block):** cutouts sliding or snapping into place; one dominant flat color field; marker circles, underlines and arrows drawing themselves; unlabeled paper bar or line charts growing; flat maps with routes and pulsing dots; colored bars sliding over areas; a spotlight vignette isolating one cutout; one object multiplying into rows to show scale.
- **Motion:** snappy ease-out entrances with slight overshoot, slow push-ins on the key beat, page-flip or whip transitions, parallax between paper layers; only one element moves loudly at a time.
- **SWATCH (custom key):** Style swatch for an editorial mixed-media collage explainer video: flat warm mustard-yellow and off-white paper background with a fine halftone dot texture, black-and-white archival photo cutouts with rough white torn-paper borders, strips of masking tape, hand-drawn black marker circles and arrows, bold flat shapes in deep navy and coral red, a small abstract bar chart made of paper strips, soft drop shadows. Abstract composition only: no letters, no words, no numbers, no logos. Flat graphic magazine-spread look, not photorealistic, not 3D.

Example SHOT: "a black-and-white cutout of a smartphone slides in from the left and snaps into place, then a laptop cutout pops in beside it; a black marker line draws itself from each device down to a small flat green island on a navy paper ocean, and the island pulses."

## Style: Diorama

A handmade miniature world of aged newspaper and cardboard, lit like a film set.
Best for geopolitics, money, power, history, or anything "cinematic".

- **STYLE:** cinematic paper diorama matching the reference image exactly: a miniature world of aged sepia newspaper and cardboard, monochrome halftone cutouts, one single burnt-orange paper accent, distressed letterpress texture, warm tungsten light, macro tilt-shift shallow depth of field, film grain and dust, handcrafted stop-motion feel.
- **NEGATIVE:** no readable text, no letters, no numbers, no logos, not photorealistic, no live-action people.
- **Devices:** people as monochrome cutout figures with black bars over their eyes (never recognizable faces); the recurring object as the single burnt-orange accent; landscapes of torn newsprint dunes, canyons and cities; queues and crowds of tiny paper figures or objects for scale.
- **Motion:** low FPV glides that rise at the key moment, slow crane-ups that reveal scale, pull-backs that turn the scene into a tiny part of a vast paper world.
- **SWATCH (custom key):** Style swatch for a cinematic paper-diorama documentary: a miniature handmade world built from aged sepia newspaper and brown cardboard, layered torn-paper hills and canyon walls, tiny monochrome cutout figures in suits with black bars over their eyes, one single burnt-orange paper object as the only color accent, distressed letterpress print texture, warm tungsten spotlight with deep shadows, macro tilt-shift shallow depth of field, film grain and floating dust. No readable letters, no words, no numbers, no logos. Not photorealistic.

Example SHOT: "a long burnt-orange paper container ship slowly swings sideways and wedges diagonally across a canal carved through torn-newspaper dunes; low FPV camera glides along the water toward it."

## When something goes wrong

- **Clip looks photoreal or loses the style:** keep the reference image attached,
  restate the STYLE and NEGATIVE lines, re-run that block. Two identical failures
  mean the prompt is the problem, not the seed: rewrite the SHOT.
- **Clip fails with no reason, or is blocked:** usually moderation. Remove named
  real people and close-up faces (use anonymous cutouts) and swap violent imagery
  for a symbol (a crack, an empty chair). Failed clips are refunded automatically.
- **Readable text appears in a clip:** re-run with the NEGATIVE line moved to the
  start of the prompt. Never rely on generated lettering.
- **Assembly rejects blocks:** follow the per-block messages (re-voice shorter or
  replace the clip), then assemble again with all items in order.
- **Balance runs out:** stop, tell the user what is finished, and list what is left.

## Delivery

Send the final mp4 link, the topic and angle in one sentence, the full script
(so the user can reuse it), and the Sources list. Offer, without running it,
a title, description and tags for YouTube or TikTok.
