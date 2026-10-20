# Multimodal teardown — let a vision model take the reference apart

`reference-teardown.md` turns impressions into **numbers**. This file turns them into **semantics**:
what a shot is doing, how it is acted, why a viewer believes it. Numbers find *where* it is wrong;
semantics find *what to do*.

Run both. They answer different questions and neither replaces the other.

## Why a vision model

A frame-difference pass says "shot 7 has low internal motion". It cannot say "shot 7 is a user
testimonial laid over a real photo, and that is why it is believable". That gap is exactly where
"the motion feels weak" and "it looks like a PPT" come from. A multimodal model closes it, **if you
feed it the film in a shape it can actually read**.

## The pipeline (two scripts)

```
video ──make_frame_sheets.py──▶ timestamped contact sheets ──vision_teardown.py──▶ per-pass JSON
                                        (overview + 9-cell / 6–8s boards)         (7 angles)
```

### 1. Cut the film into timestamped contact sheets

```bash
python3 scripts/make_frame_sheets.py ref.mp4 \
  --out sheets/ref --label "Vendor X launch" --window 8 --grid 3
```

Produces `overview.jpg` (16 cells across the whole film) and `fine-NN_*.jpg` (a 9-cell board every
~8s). **Every cell is stamped with its exact time** — that stamp is what lets the model build a
timeline instead of guessing. `sheet_manifest.json` records the same timestamps for the script.

Why not send the video file itself? Because a single frame-grid is what makes the model reason
*across time* — cells become a storyboard it can narrate in order.

### 2. Run the multi-angle pass

```bash
VISION_ENDPOINT=... VISION_MODEL=... VISION_API_KEY=... \
  python3 scripts/vision_teardown.py \
  --sheets sheets --out analyses --ours my-film --jobs 2
```

Seven angles, each a separate JSON:

| Pass | Question it answers |
|---|---|
| `structure` | shot-by-shot meaning; 3–5 acts; narrative arc; opening hook & ending |
| `camera` | move type per beat, framing, **transitions**, and what keeps moving inside a shot |
| `typography` | every readable line in time order, hierarchy, tone (product words vs user words) |
| `color` | palette + hex, saturation/contrast, whether color carries the arc |
| `authenticity` | real UI vs illustration ratio, how capability is *proved*, any fake-UI smell |
| `transferable` | what is **specifically reusable** vs what needs their budget |
| `improve_ours` | feeds the reference **and your film** in one request → a concrete fix list |

`improve_ours` is the payoff: same prompt, reference on one side, your frames on the other, output
is "reference does X → we currently do Y → change Z".

### 3. Take apart at least 3 references, then keep only the shared rules

One reference teaches you one company's taste. Three teach you the **settings everyone shares** —
those are the rules. In the run behind this file, five films were torn down and four findings were
identical across all five (see `multimodal-teardown.md` §Shared rules below).

## Calling the vision model

Most modern multimodal endpoints accept a **whole video** natively through an OpenAI-compatible
`chat/completions` body. The shape below is the one validated for this skill (on a MiMo-V2.6
endpoint); other vision models accept the same `video_url` block or an equivalent:

```jsonc
POST /v1/chat/completions
{ "model": "<your-vision-model>",
  "messages": [{ "role":"user", "content": [
    { "type":"video_url", "video_url":{"url":"https://.../x.mp4"},
      "fps": 2, "media_resolution": "default" },
    { "type":"text", "text":"describe this video" } ]}],
  "max_completion_tokens": 1024 }
```

- URL **or** base64 (`data:video/mp4;base64,…`, ≤50 MB); URL single file ≤300 MB.
- Audio uses `{"type":"input_audio","input_audio":{"data":"<url|base64>"}}`.
- **`stream: true` is mandatory** — non-stream calls come back SSE-wrapped with empty `choices`.
- Set the endpoint/model via `VISION_ENDPOINT` / `VISION_MODEL` / `VISION_API_KEY`; any
  OpenAI-compatible multimodal endpoint works.

**Two traps to check before trusting a run:**

1. **A gateway may drop non-text blocks.** Routed through an OpenAI-compatible relay, image blocks
   worked but `video_url` / `input_audio` were rejected by a synthesised guard
   (`chatcmpl-unsupported-guard`) even though the channel advertised `vision` + `audio_input`.
   The failure mode is nasty: it returns **HTTP 200 with a friendly assistant message**, so a naive
   caller records a "success" and an empty result. Always assert the response actually contains a
   description, not just that the call returned.
2. **If video is blocked, degrade to frames — it is not a dead end.** `make_frame_sheets.py`
   (multi-image) + a separate ASR pass for audio reproduces most of the value. The frame path is
   also cheaper and gives you the timestamps for free.

## Shared rules extracted from a real 5-film run

These came out identical across Anthropic (Opus 4.6 / Fable 5.1 / Cowork) and OpenAI (GPT-6 /
Codex CLI) — treat them as counts, not taste:

1. **The protagonist is a person or one person's action — never the UI by itself.** User testimonial
   cards, a lone cursor as "the only actor", a presenter beside a terminal. A film with no human
   throughline reads as a slide deck no matter how good the UI is.
2. **One claim per screen.** One headline + at most one supporting line, with ≥2× type-size
   difference. Six stacked layers (title / number / two lines / page number / watermark) is the
   single most common amateur tell.
3. **Breathing.** Fast cuts (1.5–2s) earn urgency in the problem section; a reveal or the closing
   line **holds 2–4s of near-stillness** so the claim lands. Uniform pacing reads as flat.
4. **Colour is a closed system.** Low-saturation base + **one** high-saturation accent, accent share
   under ~5%, and the accent means something (e.g. red = the pain, withdrawn in the solution
   section, returned at the close).

Plus two cheap, high-yield devices worth stealing directly: **giant-type as a metronome** (swap a
full-screen line every ~0.7–1.3s) and **a progress checklist that ticks**. Both need only code.

## Honesty rules

- **A screenshot is not proof of a capability.** If a number cannot be traced to a real source, mark
  it; a "real demo data" watermark proves nothing — evidence does.
- **Never let the model invent what it cannot read.** Ask for "readable text only"; a small or
  clipped line must come back as "unclear", not guessed.
- **Do not fabricate the model's findings.** If a call failed or was guarded, write "not measured",
  not a plausible-sounding summary.
