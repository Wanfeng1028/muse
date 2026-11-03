# File formats

Four files, and an optional shots.json with sketches, written to the working folder. Other tools parse them exactly, so keep the shapes below. UTF-8, LF line endings.

## brief.md

```
---
status: draft            # draft | confirmed
message: "..."
audience: "..."
platform: shorts         # shorts | reels | tiktok | youtube | linkedin | x
aspect: "9:16"
length: 45s
tone: "..."
angle: "..."
---
## Intent
(the user's own words, quoted)

## Script
One spoken sentence per line.

## Outline
- point [1]

## Stated
- message: ... — "user quote"

## Inferred
- aspect: 9:16 — shorts default

## Notes
```

- Frontmatter is flat `key: value`. Quote strings that contain `:` or `#`. Unknown keys are allowed and must be kept when you edit.
- `status` is `draft` until the user says yes, then `confirmed`.
- `length` is a number plus `s` (`45s`) or minutes (`2m`). `aspect` is quoted (`"9:16"`, `"16:9"`, `"1:1"`, `"4:5"`).
- Sections may be absent. Use these exact `##` headings. Anything else goes under `## Notes`.
- `## Script`: one spoken sentence per line, no blank lines inside, no markdown, no stage directions.
- `## Stated` and `## Inferred`: bullets `- field: value — "quote"` or `- field: value — reason`.
- `## Outline`: bullets, each ending in `[n]` when it makes a factual claim.

## research.md

```
# <topic>

- Claim in one line. [1]
- Another claim. [2][3]

## Angles

### <title>
Hook: the first spoken line
Why now: the reason, grounded in a source. [2]
```

- The H1 is the topic. Then bullets, every claim ending in `[n]` that matches `sources.json`.
- `## Angles` is optional. Each angle has `### title`, a `Hook:` line and a `Why now:` line that ends in `[n]`.

## sources.json

```json
[{"n":1,"url":"https://example.com/post","title":"...","site":"example.com","date":"2026-10-17","quote":"at most 25 words, verbatim","fetchedAt":"2026-10-18T10:00:00Z"}]
```

- A JSON array. `n` starts at 1 and matches the `[n]` markers. `url` is the page you fetched.
- `date` is the publish date `YYYY-MM-DD`, or `null` when the page doesn't show one. `fetchedAt` is UTC ISO 8601.
- `quote` is verbatim from the page, at most 25 words, or an empty string.
- No entry for a page you did not read.

## topics.json

```json
{"date":"2026-10-18","prompt":"daily AI news","topics":[{"title":"...","hook":"...","whyNow":"...","sources":[{"url":"...","title":"..."}]}]}
```

- `date` is today, `prompt` is the standing prompt (or `""` when there was none).
- 3 to 7 topics, newest first. `hook` is the first spoken line. `whyNow` is one sentence grounded in a listed source.
- Every topic lists at least one source you fetched. Topics that you could not source don't go in.

## shots.json and shots/NN.svg (optional)

Only when asked to split the script into shots, after `brief.md` has a `## Script`. Like a storyboard: the person records one shot at a time with its sketch beside the lines.

```json
{"aspect":"9:16","shots":[{"n":1,"from":1,"to":2,"framing":"close","note":"leans in on the hook","sketch":"shots/01.svg"}]}
```

- `aspect` is the brief's (`"9:16"`, `"16:9"`, `"1:1"`, `"4:5"`); `9:16` when it has none.
- `from` and `to` are 1-based line numbers of the `## Script` section (one spoken sentence per line, as in brief.md). Together the shots cover every line once, in order, with no overlap. Usually 3 to 10 shots.
- `n` is 1 to 99, unique. `sketch` is `shots/NN.svg` with `NN` the two-digit `n`.
- `framing` is one of `close`, `medium`, `wide` (the speaker, nearer to farther), `screen` (a screen recording, the speaker small or absent), `broll` (a cutaway clip), `text` (a full-frame text or number card). `note` is a few words on what the picture does.
- Each sketch is a plain SVG line drawing:
  - `viewBox` `0 0 90 160` for 9:16, `0 0 160 90` for 16:9, `0 0 100 100` for 1:1, `0 0 100 125` for 4:5.
  - Strokes in `currentColor` only; every fill is `none`. At most 40 elements, at most 20 KB, no text longer than 4 words.
  - No `<script>`, `<foreignObject>`, `<image>`, `<use>`, `<style>`, comments, `href`, `on*` attributes or external references.
  - The speaker is a simple head-and-shoulders silhouette sized by the framing; a screen is a rounded rect with a few lines; b-roll is a crossed box with a 1 to 3 word label; a text card is 2 or 3 bars.
- Leave `brief.md` as it is.
