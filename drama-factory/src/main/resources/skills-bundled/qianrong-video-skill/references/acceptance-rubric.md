# Acceptance rubric — the reusable pass line

Write this **before** building anything. It defines what "excellent" means for this film, so
"is it better now" stops being a feeling and becomes a check.

## 1. One-line definition

**An excellent product promo = for the least cognitive cost, make the target viewer remember one
value proposition within 30 seconds — and believe it.**

Three things, all required:

- **Memorable** — one claim, not a feature list.
- **Believable** — real UI / real numbers as evidence, not decorative stock.
- **Watchable** — pacing and density match the channel it ships on.

The one thing every bad promo shares: **lots of information, nothing remembered.** It reads like a
spoken feature list.

## 2. Weighted dimensions (total 100, default pass line 90)

| # | Dimension | Weight | Full marks | Failing |
|---|---|---|---|---|
| A | Narrative / claim | 25 | Hooked in first 3s, claim lands before the 2nd beat, the rest is evidence | Opens on company/features; nothing remembered |
| B | Believability | 20 | Real UI, real numbers, verifiable features | Fake UI, invented numbers, claims the product can't back |
| C | Visual design | 20 | Uses the product's own design system; ≥3 layers; two focal points; texture even on light backgrounds | Flat empty background, centered stack, generic AI gradient look |
| D | Motion / pacing | 15 | build→breathe→resolve; varied easing and duration; beat-accurate | Everything fades up together; one transition everywhere |
| E | Sound / beat | 10 | Music and cut share a pulse; key actions hit accents; clean mix | Music is just filler; cuts drift off the beat |
| F | Finish / technical | 10 | lint/check clean, no overflow, no black frames, contrast passes, exact length | Text overflow, missing elements, wrong length |

**Verdict:** total ≥ 90 **and** no hard-veto item → pass. Adapt the weights; keep the shape.

## 3. Hard-veto list (any one fails, regardless of score)

1. A capability the product does not have, or invented customers/numbers.
2. Mock UI presented as the real product.
3. Leaked credentials, cookies, real account info, internal hosts/domains/repo names.
4. Unlicensed or (where required) unattributed assets or music.
5. Text overflowing, clipped, or occluded by another element.
6. Full-screen text below contrast threshold, or any unreadable frame.
7. Music of untraceable / unclear provenance.
8. Length or aspect ratio off the delivery spec.
9. A third-party trademark used as your own brand or implying endorsement.

Palette / type / motion specifics are taste and belong in your creative brief, not here.

## 4. Checkpoints

| Gate | When | What it checks |
|---|---|---|
| G1 Storyboard | Before writing composition code | Dimension A: claim, structure, per-shot responsibility |
| G2 Keyframes | Layout done, before motion | Dimension C: key-frame layout and brand consistency |
| G3 Final | After render | Everything + veto list + full contact sheet |

G3 deliverable = lint/check output, a contact sheet, and a per-dimension scorecard.
