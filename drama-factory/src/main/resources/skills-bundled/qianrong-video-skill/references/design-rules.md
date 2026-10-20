# Design rules — what every good product film does

These are not opinions. They were extracted by tearing down **five big-company AI-product launch
films** (Anthropic Opus 4.6 / Fable 5.1 / Cowork, OpenAI GPT-6 / Codex CLI) with both a
frame-measurement pass and a vision-model pass, then checking which findings **repeated across all
five**. A rule here appears in every reference film tested; if it only appeared in one, it is that
company's taste, not a rule.

Measured on the same five films (numbers from `scripts/teardown_video.py`):

| Metric | Opus 4.6 | Fable 5.1 | Cowork | GPT-6 | Codex CLI |
|---|---|---|---|---|---|
| Duration | 39.4s | 85.4s | 68.6s | 70.1s | 194s |
| Shots | 14 | 29 | 9 | 31 | 27 |
| Avg shot | 2.80s | 2.93s | 7.56s | 2.26s | 7.2s |
| In-shot motion | 0.82 | 0.71 | 0.37 | 1.75 | 0.74 |
| Motion coverage | 0.17 | 0.21 | 0.09 | 0.47 | 0.17 |

Note the third row: **shot length alone is not the discriminator** — two films have long shots like
a weak film. What separates them is what happens *inside* the shot. That is rule 2 below.

---

## The four rules

### 1. The protagonist is a person, or one person's action — never the UI by itself

Every reference film has a human throughline. Opus 4.6 cuts away to real user testimonial cards
(avatar + handle + one line) over real footage. Cowork makes **a lone cursor the only actor** — it
moves, clicks, and the viewer follows it. Codex CLI puts a presenter beside a terminal. None of them
is a silent slideshow of product screens.

**Why it matters:** a film with no human anchor is read as a screen recording, not a story. The
viewer has nobody to identify with and nothing to follow.

**How to apply it when you have no actors, no budget, and only real screenshots:**
- Make the **cursor the actor**. One visible cursor that moves with easing, hovers before it clicks,
  and compresses on press is the cheapest "someone is really using this" signal that exists.
- Write copy in the **first person of the user** ("I saved it, then never opened it again"), not the
  product's voice ("multi-platform collection management").
- If you have any real footage of hands or a person, one 1.5–2s insert in the problem section
  anchors the whole film.

### 2. Something must be moving inside every shot

This is the rule the table above is actually measuring. A long shot is fine **if it is alive**;
a shot is dead when the frame stops changing. The reference films keep 1.5–4× more in-shot motion
than a typical "static screenshot with a fade" edit.

**Three layers is the working recipe** (used in the starter, verified in the reference films):
1. **Camera** — a slow push/pull/pan on the whole scene (`scale 1.04→1.08`, 8s, linear). This alone
   fixes "it looks like a still".
2. **Ambient** — a grid drift, a ghost-word parallax, a pulse. Something always moving in the
   background.
3. **Content** — the number counting, the text typing, the queue advancing, the cursor moving.

**Audit it:** `audit_video.py` reports **frozen** (whole-frame mean diff < 0.15) and **low-motion**
(active-block share < 2%) as two separate signals. Aim for frozen = 0 and watch low-motion. A frame
where only the ambient layer moves is *not* fixed — it is a "low-motion" frame and the viewer reads
it as stuck.

### 3. One claim per screen, and hold the close

The reference films show **one** headline per screen, with at most one supporting line and a type-size
gap of ≥2×. Information density above that reads as a slide the viewer has to study, not a film they
watch.

Two halves to this rule:
- **Fast cuts earn urgency.** The problem/pain section runs 1.5–2s per screen.
- **The close holds.** After the reveal, the film holds a near-still frame for **2–4s** so the claim
  lands. Codex CLI and Cowork both end on a single line held for several seconds with no CTA clutter.

**How to apply it:** enforce a single `h1` per scene in the markup. Demote everything else: the page
number, the watermark, the second line of copy. If a screen has six layers of text, delete four.

### 4. Colour is a closed system

Low-saturation base + **one** high-saturation accent, accent share under ~5%, and the accent **means
something** and moves with the story. In the reference set, red means the pain: it appears in the
problem section, is withdrawn during the solution, and returns at the close — colour carries the arc.

The failure mode is an accent used everywhere: red numbers + red headline + red button on the same
screen is visual noise, not emphasis.

**How to apply it:** define three CSS variables (`--paper`, `--ink`, `--accent`) and map everything
else to them. Let one timeline section use the accent at a time.

---

## Two cheap devices worth stealing outright

Both need only code and both showed up repeatedly in the reference films.

**Giant-type as a metronome.** Swap a full-screen line every 0.7–1.3s. The size contrast and the
speed create an "information flow" feel with zero assets. (Opus 4.6 uses this for its first 4
seconds; the same trick works as a mid-film rhythm reset.)

**A progress checklist that ticks.** A list where each row checks off every ~1.2s. It reads as "the
product is really doing work", is the most information-dense frame in Cowork, and needs no footage —
just markup and a timeline. This is the single best "small team, no assets" scene in the set.

---

## Applying this to your own film

1. Read this file before designing. It is cheaper than rediscovering the rules.
2. Run the starter (`assets/starter/my-film/`) to confirm your toolchain, then edit it.
3. Tear down ≥3 references in your product's medium (see `multimodal-teardown.md`) and compare your
   film's numbers to theirs with `teardown_video.py`.
4. Adopt a rule only if it repeats across ≥3 references **and** you can point to a frame that proves
   your film violates or satisfies it.

## Honesty rules that ride along with these

- **A screenshot is not proof of a capability.** If a number can't be traced to a real source, mark
  it. A "real demo data" watermark proves nothing — evidence does.
- **Never present mock UI as the real product.** Draw illustrative UI only if it is clearly labelled
  as illustration, never wearing the product's chrome.
- **Never let the model, or yourself, invent a finding.** If a measurement failed or a call was
  blocked, write "not measured", not a plausible-sounding number.
