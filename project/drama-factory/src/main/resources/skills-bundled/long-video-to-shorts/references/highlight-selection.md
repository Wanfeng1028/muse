# Highlight selection — how the agent picks moments

You (the agent) are the "virality model". Read `work/transcript.json` (flat
`words[]` + `segments[]`) and choose the segments that will work as standalone
shorts. Then write `work/clips.json` and present the shortlist for the user to
approve BEFORE any render.

## Scoring rubric (score each candidate 0–3 per dimension)

| Dimension | 3 = strong | 0 = weak |
|---|---|---|
| **Hook** | grabs in the first ~3s: a question, bold claim, number, "voici pourquoi…" | slow ramp, throat-clearing, "euh donc voilà" |
| **Self-containment** | understandable with zero prior context | starts mid-thought, dangling "ça"/"comme je disais" |
| **Payoff** | a punchline, reveal, tension→release, concrete takeaway | trails off, no resolution |
| **Energy / emotion** | vivid, opinionated, surprising | flat, list-y, filler |
| **Length fit** | lands at 12–60s on sentence boundaries | needs >60s to make sense |

Keep every candidate whose total is solid (≈ ≥ 10/15) — the user asked for "as
many as hold up", so don't cap arbitrarily; list them all and let the user trim.

## Boundary rules (non-negotiable)

- **Never cut mid-sentence.** Snap `start`/`end` to sentence boundaries using the
  word timestamps + `segments[]`. Prefer starting on the first word of a sentence
  and ending on the last word's `end` (+ ~0.3s tail).
- **≤ 60s hard cap.** If a great moment runs long, tighten to its core.
- **≥ ~12s** or it's too thin to post.
- Avoid segments that reference off-screen visuals the crop will lose.

## Writing clips.json

For each kept segment set:
- `start`/`end` — `HH:MM:SS.mmm`, on sentence boundaries.
- `kind` — `facecam` or `screen` (from the PROBE classification of that time range).
- `title` — a punchy FR hook headline (≤ ~18 chars/line, 2 lines max after wrap).
- `face_center_x` — facecam only; see `reframe.md` (sample a frame, look, set 0..1).
- `caption_identity` — facecam only; recommend one from the embedded-captions
  CATALOG (default `anchor`). The user may override.
- `reason` — one line; shown in the approval table.

## Approval table to present

Render a compact table: `id | start–end | kind | title | reason`. Ask the user to
keep / drop / adjust. Only build the approved set.
